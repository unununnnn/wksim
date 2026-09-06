#include "WksimVisualGameMode.h"
#include "AssetCompilingManager.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Common/UdpSocketBuilder.h"
#include "Components/SceneComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Components/SkyAtmosphereComponent.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Materials/MaterialInterface.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "UnrealClient.h"

IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, WksimVisual, "WksimVisual");

namespace
{
bool VectorField(const TSharedPtr<FJsonObject>& Object, const TCHAR* Name, int32 Length, TArray<double>& Values)
{
    const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
    if (!Object->TryGetArrayField(Name, Items) || Items->Num() != Length) return false;
    for (const auto& Item : *Items)
    {
        double Value = 0.0;
        if (!Item->TryGetNumber(Value) || !FMath::IsFinite(Value)) return false;
        Values.Add(Value);
    }
    return true;
}
}

AWksimVisualGameMode::AWksimVisualGameMode()
{
    PrimaryActorTick.bCanEverTick = true;
    DefaultPawnClass = nullptr;
    HUDClass = AWksimHud::StaticClass();
}

UStaticMeshComponent* AWksimVisualGameMode::AddPart(const FString& Name, const TCHAR* Asset,
    const FVector& Location, const FVector& Scale, const FRotator& Rotation)
{
    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, Asset);
    if (!Mesh)
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM_MODEL required mesh missing: %s"), Asset);
        FPlatformMisc::RequestExitWithStatus(true, 22);
        return nullptr;
    }
    UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(Vehicle, *Name);
    Part->SetStaticMesh(Mesh);
    Part->SetMobility(EComponentMobility::Movable);
    Part->SetupAttachment(Vehicle->GetRootComponent());
    Part->SetRelativeLocation(Location);
    Part->SetRelativeRotation(Rotation);
    Part->SetRelativeScale3D(Scale);
    Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Part->SetSimulatePhysics(false);
    Part->RegisterComponent();
    return Part;
}

void AWksimVisualGameMode::BeginPlay()
{
    Super::BeginPlay();
    int32 Port = 19060;
    FParse::Value(FCommandLine::Get(), TEXT("WksimPort="), Port);
    if (!FParse::Value(FCommandLine::Get(), TEXT("WksimRunId="), RunId) || RunId.IsEmpty() || RunId.Len() > 64 ||
        !FParse::Value(FCommandLine::Get(), TEXT("WksimVehicle="), VehicleId) ||
        !(VehicleId == TEXT("1") || VehicleId == TEXT("px4") || VehicleId == TEXT("arducopter")) || Port < 1024 || Port > 65535)
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM invalid launch identity/port"));
        FPlatformMisc::RequestExitWithStatus(true, 20);
        return;
    }
    FParse::Value(FCommandLine::Get(), TEXT("WksimCaptureDir="), CaptureDirectory);
    for (int32 Index = 0; Index < RunId.Len(); ++Index)
    {
        const TCHAR Character = RunId[Index];
        const bool ProductChar = (Character >= '0' && Character <= '9') ||
            (Character >= 'a' && Character <= 'z') || (Character >= 'A' && Character <= 'Z') ||
            (Index > 0 && (Character == '_' || Character == '-'));
        const bool LegacyChar = RunId.Len() == 32 &&
            ((Character >= '0' && Character <= '9') || (Character >= 'a' && Character <= 'f'));
        if (!(VehicleId == TEXT("1") ? ProductChar : LegacyChar))
        {
            UE_LOG(LogTemp, Error, TEXT("WKSIM invalid run identity characters"));
            FPlatformMisc::RequestExitWithStatus(true, 20);
            return;
        }
    }
    if (!CaptureDirectory.IsEmpty()) IFileManager::Get().MakeDirectory(*CaptureDirectory, true);
    Socket = FUdpSocketBuilder(TEXT("WksimViewOnlyLoopback")).AsNonBlocking()
        .BoundToEndpoint(FIPv4Endpoint(FIPv4Address::InternalLoopback, static_cast<uint16>(Port)))
        .WithReceiveBufferSize(256 * 1024);
    if (!Socket)
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM UDP bind failed"));
        FPlatformMisc::RequestExitWithStatus(true, 21);
        return;
    }
    // The reused visual map's helipad top is +34 cm. Align that surface with
    // the independent model's z=0 plane; never add a bias to physical truth.
    // Buildings remain visual-only until the scene collision interface exists.
    for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
    {
        UStaticMeshComponent* Mesh = It->GetStaticMeshComponent();
        if (Mesh->GetStaticMesh() && Mesh->GetStaticMesh()->GetName() == TEXT("SM_UrbanBlock_Original"))
        {
            Mesh->SetMobility(EComponentMobility::Movable);
            It->SetActorLocation(FVector(0, 0, -34));
            UE_LOG(LogTemp, Display, TEXT("WKSIM_SCENE helipad_surface_z_cm=0 decoration_offset_z_cm=-34 collisions=visual_only"));
        }
    }
    GetWorld()->SpawnActor<ASkyAtmosphere>();
    Vehicle = GetWorld()->SpawnActor<AActor>();
    USceneComponent* Root = NewObject<USceneComponent>(Vehicle, TEXT("AuthoritativePose"));
    Vehicle->SetRootComponent(Root);
    Root->SetMobility(EComponentMobility::Movable);
    Root->RegisterComponent();
    // Prometheus P450 source geometry, with source SDF rotor origins retained.
    // Geometry-only floor alignment never changes the authoritative Actor pose.
    // This is a P450 visual, not a claim that baseline quad-X physics is calibrated
    // to P450 inertial/aerodynamic parameters. See p450-visual-manifest.json.
    UMaterialInterface* BodyMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Wksim/P450/M_P450_Body.M_P450_Body"));
    UMaterialInterface* RotorMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Wksim/P450/M_P450_Rotor.M_P450_Rotor"));
    if (!BodyMaterial || !RotorMaterial)
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM_MODEL required P450 material missing"));
        FPlatformMisc::RequestExitWithStatus(true, 22);
        return;
    }
    const FVector GeometryOffset(0, 0, 4.4560544192790985);
    UStaticMeshComponent* Body = AddPart(TEXT("P450Body"), TEXT("/Game/Wksim/P450/SM_p450.SM_p450"), GeometryOffset, FVector::OneVector);
    if (!Body) return;
    Body->SetMaterial(0, BodyMaterial);
    const FVector Motors[] = {FVector(14.65, 14.7, 15.1), FVector(-14.65, -14.7, 15.1),
                             FVector(14.65, -14.7, 15.1), FVector(-14.65, 14.7, 15.1)};
    const TCHAR* MotorNames[] = {TEXT("FR"), TEXT("RL"), TEXT("FL"), TEXT("RR")};
    for (int32 Index = 0; Index < 4; ++Index)
    {
        UStaticMeshComponent* Rotor = AddPart(FString::Printf(TEXT("P450Rotor_%s"), MotorNames[Index]),
            Index < 2 ? TEXT("/Game/Wksim/P450/SM_p450_ccw.SM_p450_ccw") : TEXT("/Game/Wksim/P450/SM_p450_cw.SM_p450_cw"),
            Motors[Index] + GeometryOffset, FVector::OneVector);
        if (!Rotor) return;
        Rotor->SetMaterial(0, RotorMaterial);
        Rotors.Add(Rotor);
        RotorRpm.Add(0.0);
        UE_LOG(LogTemp, Display, TEXT("WKSIM_MODEL rotor=%s source_sdf_index=%d origin_cm=%s yaw_sign=%d"),
            MotorNames[Index], Index, *Rotor->GetRelativeLocation().ToString(), Index < 2 ? -1 : 1);
    }
    Camera = GetWorld()->SpawnActor<ACameraActor>();
    Camera->SetActorLocation(FVector(-280, -320, 220));
    Camera->SetActorRotation((FVector(0, 0, 60) - Camera->GetActorLocation()).Rotation());
    Camera->GetCameraComponent()->SetFieldOfView(65.0f);
    if (auto* Controller = GetWorld()->GetFirstPlayerController()) Controller->SetViewTarget(Camera);
    // This map was authored with Stationary lights. The runtime moves the scene
    // mesh and vehicle without baked lightmaps; a Movable sun supplies the direct
    // lighting path here. Preserve the map's color, direction and intensity.
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        TInlineComponentArray<UDirectionalLightComponent*> Lights(*It);
        for (auto* Light : Lights)
        {
            Light->SetMobility(EComponentMobility::Movable);
            UE_LOG(LogTemp, Display, TEXT("WKSIM_LIGHT sun=movable intensity=%.4f rotation=%s"),
                Light->Intensity, *Light->GetComponentRotation().ToString());
        }
    }
    LaunchPort = Port;
    UE_LOG(LogTemp, Display, TEXT("WKSIM_STARTING run=%s vehicle=%s port=%d world=%s"),
        *RunId, *VehicleId, Port, *GetWorld()->GetMapName());
}

bool AWksimVisualGameMode::ApplyPacket(const uint8* Bytes, int32 Count, FString& Ack)
{
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes), Count);
    TSharedPtr<FJsonObject> Object;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FString(Text.Length(), Text.Get())), Object) || !Object) return false;
    FString Run, Id;
    double Version = 0, Sequence = 0, Time = 0;
    TArray<double> P, Q, Rpm;
    const bool Product = VehicleId == TEXT("1");
    if (Product)
    {
        double NumericId = 0, Wall = 0, OriginalWall = 0;
        FString DisplayClock;
        const FDateTime Now = FDateTime::UtcNow();
        const double WallNow = static_cast<double>(Now.ToUnixTimestamp()) + Now.GetMillisecond() / 1000.0;
        if (!Object->TryGetNumberField(TEXT("vehicle_id"), NumericId) || NumericId != 1 ||
            !Object->TryGetNumberField(TEXT("source_wall_time_s"), OriginalWall) || !FMath::IsFinite(OriginalWall) || OriginalWall < 0 ||
            !Object->TryGetStringField(TEXT("display_clock"), DisplayClock) || DisplayClock != TEXT("windows_utc_bound") ||
            !Object->TryGetNumberField(TEXT("display_wall_time_s"), Wall) || !FMath::IsFinite(Wall) ||
            WallNow - Wall > 0.75 || WallNow - Wall < -0.25) return false;
        const TCHAR* Keys[] = {TEXT("position_frame"), TEXT("position_unit"), TEXT("quaternion_order"),
            TEXT("body_frame"), TEXT("rotor_unit"), TEXT("configuration")};
        const TCHAR* Values[] = {TEXT("NED"), TEXT("m"), TEXT("WXYZ"), TEXT("FRD"), TEXT("rpm"), TEXT("quad-X")};
        for (int32 Index = 0; Index < 6; ++Index)
        {
            FString Value;
            if (!Object->TryGetStringField(Keys[Index], Value) || Value != Values[Index]) return false;
        }
        const TArray<TSharedPtr<FJsonValue>>* Order = nullptr;
        if (!Object->TryGetArrayField(TEXT("rotor_order"), Order) || Order->Num() != 4) return false;
        const TCHAR* Motors[] = {TEXT("FR"), TEXT("RL"), TEXT("FL"), TEXT("RR")};
        for (int32 Index = 0; Index < 4; ++Index)
        {
            FString Value;
            if (!(*Order)[Index]->TryGetString(Value) || Value != Motors[Index]) return false;
        }
    }
    if (!Object->TryGetNumberField(TEXT("version"), Version) || Version != (Product ? 2 : 1) ||
        !Object->TryGetStringField(TEXT("run_id"), Run) || Run != RunId ||
        (!Product && (!Object->TryGetStringField(TEXT("vehicle_id"), Id) || Id != VehicleId)) ||
        !Object->TryGetNumberField(TEXT("sequence"), Sequence) || !FMath::IsFinite(Sequence) ||
        Sequence < 0 || Sequence > 9007199254740991.0 || FMath::FloorToDouble(Sequence) != Sequence ||
        Sequence <= LastSequence || !Object->TryGetNumberField(TEXT("sim_time_s"), Time) ||
        !FMath::IsFinite(Time) || Time < 0 || (LastSequence >= 0 && Time <= SourceTime) ||
        !VectorField(Object, TEXT("position_ned_m"), 3, P) ||
        !VectorField(Object, TEXT("quaternion_wxyz"), 4, Q) ||
        !VectorField(Object, TEXT("rotor_rpm"), 4, Rpm)) return false;
    const FQuat NedQ(Q[1], Q[2], Q[3], Q[0]);
    if (FMath::Abs(NedQ.SizeSquared() - 1.0) > 1e-5 ||
        FMath::Max3(FMath::Abs(P[0]), FMath::Abs(P[1]), FMath::Abs(P[2])) > 1000000.0) return false;
    for (double Value : Rpm) if (Value < 0 || Value > 100000) return false;
    // NED/FRD -> UE left-handed X-forward, Y-right, Z-up, centimetres.
    const FQuat UeQ(-Q[1], -Q[2], Q[3], Q[0]);
    Vehicle->SetActorLocationAndRotation(FVector(P[0] * 100, P[1] * 100, -P[2] * 100), UeQ,
        false, nullptr, ETeleportType::TeleportPhysics);
    PositionNed = FVector(P[0], P[1], P[2]);
    SourceTime = Time;
    if (Product) Object->TryGetNumberField(TEXT("display_wall_time_s"), DisplayWallTime);
    LastSequence = static_cast<int64>(Sequence);
    LastReceivedWall = FPlatformTime::Seconds();
    RotorRpm = Rpm;
    const FVector Actual = Vehicle->GetActorLocation();
    const FQuat ActualQ = Vehicle->GetActorQuat();
    Ack = FString::Printf(TEXT("{\"run_id\":\"%s\",\"sequence\":%lld,\"sim_time_s\":%.9f,\"rejected\":%lld,"
        "\"ue_position_cm\":[%.9f,%.9f,%.9f],\"ue_quaternion_xyzw\":[%.9f,%.9f,%.9f,%.9f]}"),
        *RunId, LastSequence, SourceTime, Rejected, Actual.X, Actual.Y, Actual.Z, ActualQ.X, ActualQ.Y, ActualQ.Z, ActualQ.W);
    return true;
}

bool AWksimVisualGameMode::IsStale() const
{
    if (VehicleId == TEXT("1"))
    {
        const FDateTime Now = FDateTime::UtcNow();
        const double Age = static_cast<double>(Now.ToUnixTimestamp()) + Now.GetMillisecond() / 1000.0 - DisplayWallTime;
        if (Age > 0.75 || Age < -0.25) return true;
    }
    return LastSequence < 0 || FPlatformTime::Seconds() - LastReceivedWall > 0.75;
}

void AWksimVisualGameMode::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!Socket || !Vehicle) return;
    uint32 Pending = 0;
    // Bound work per frame; sender coalesces to latest state, physics never waits.
    for (int32 Read = 0; Read < 64 && Socket->HasPendingData(Pending); ++Read)
    {
        uint8 Buffer[4096];
        int32 Count = 0;
        auto Sender = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
        if (!Socket->RecvFrom(Buffer, sizeof(Buffer), Count, *Sender) || Count <= 0) break;
        FString Ack;
        if (Pending > sizeof(Buffer) || Sender->ToString(false) != TEXT("127.0.0.1") || !ApplyPacket(Buffer, Count, Ack))
        {
            ++Rejected;
            continue;
        }
        const FTCHARToUTF8 Encoded(*Ack);
        int32 Sent = 0;
        Socket->SendTo(reinterpret_cast<const uint8*>(Encoded.Get()), Encoded.Length(), Sent, *Sender);
    }
    if (!IsStale())
    {
        for (int32 Index = 0; Index < Rotors.Num(); ++Index)
            Rotors[Index]->AddLocalRotation(FRotator(0, RotorRpm[Index] * 6.0 * DeltaSeconds * (Index < 2 ? -1 : 1), 0));
    }
    const FVector Focus = Vehicle->GetActorLocation() + FVector(0, 0, 20);
    Camera->SetActorLocation(Focus + FVector(-260, -300, 120));
    Camera->SetActorRotation((Focus - Camera->GetActorLocation()).Rotation());
    const double Wall = FPlatformTime::Seconds();
    // Poll only; never wait on the render thread or connect it to the physics clock.
    // The startup signal means assets compiled + initial render submission drained,
    // not sensor calibration or assurance about every later visual frame.
    if (!bRenderReady)
    {
        if (FAssetCompilingManager::Get().GetNumRemainingAssets() > 0)
        {
            ReadyFrames = 0;
            bStartupFenceQueued = false;
        }
        else if (++ReadyFrames >= 3)
        {
            if (!bStartupFenceQueued)
            {
                StartupFence.BeginFence(FRenderCommandFence::ESyncDepth::RHIThread);
                bStartupFenceQueued = true;
            }
            else if (StartupFence.IsFenceComplete())
            {
                bRenderReady = true;
                UE_LOG(LogTemp, Display, TEXT("WKSIM_READY run=%s vehicle=%s port=%d world=%s assets_remaining=0 ready_ticks=%d fence=rhi model=P450_visual_quadX_physics"),
                    *RunId, *VehicleId, LaunchPort, *GetWorld()->GetMapName(), ReadyFrames);
            }
        }
    }
    if (bRenderReady && !CaptureDirectory.IsEmpty() && Wall > NextCaptureWall)
    {
        const FString File = FPaths::Combine(CaptureDirectory, FString::Printf(TEXT("frame-%04lld.png"), CaptureIndex++));
        FScreenshotRequest::RequestScreenshot(File, true, false);
        UE_LOG(LogTemp, Display, TEXT("WKSIM_CAPTURE %s sequence=%lld sim=%.9f stale=%d rejected=%lld"),
            *File, LastSequence, SourceTime, IsStale(), Rejected);
        NextCaptureWall = Wall + 2.0;
    }
}

void AWksimVisualGameMode::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Socket)
    {
        Socket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
        Socket = nullptr;
    }
    Super::EndPlay(Reason);
}

void AWksimHud::DrawHUD()
{
    Super::DrawHUD();
    const auto* Mode = Cast<AWksimVisualGameMode>(GetWorld()->GetAuthGameMode());
    if (!Mode || !Canvas) return;
    const FLinearColor StatusColor = Mode->IsStale() ? FLinearColor(1, .25, .15) : FLinearColor(.2, 1, .5);
    DrawRect(FLinearColor(0.025, 0.04, 0.065, .88), 20, 20, 610, 132);
    DrawText(FString::Printf(TEXT("WKSIM  |  %s  |  UE 5.5  |  VIEW ONLY"), *Mode->VehicleId), FLinearColor::White, 34, 30, GEngine->GetMediumFont(), 1.1);
    DrawText(!Mode->IsRenderReady() ? TEXT("PREPARING DISPLAY / state processing independent") :
        (Mode->IsStale() ? TEXT("STALE / waiting for authoritative state") : TEXT("LIVE / independent SITL physics")), StatusColor, 34, 64);
    DrawText(FString::Printf(TEXT("N %.3f  E %.3f  D %.3f m     SIM %.3f s"),
        Mode->PositionNed.X, Mode->PositionNed.Y, Mode->PositionNed.Z, Mode->SourceTime), FLinearColor::White, 34, 91);
    DrawText(FString::Printf(TEXT("Sequence %lld   Rejected %lld   P450 visual / quad-X physics"), Mode->LastSequence, Mode->Rejected), FLinearColor(.65, .75, .9), 34, 118);
}
