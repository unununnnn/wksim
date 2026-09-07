#include "WksimVisualGameMode.h"
#include "WksimRgbFixture.h"
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
#include "Misc/FileHelper.h"
#include "Modules/ModuleManager.h"
#include "Materials/MaterialInterface.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "UnrealClient.h"
#include "InputCoreTypes.h"

IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, WksimVisual, "WksimVisual");

namespace
{
bool IsHexIdentity(const FString& Value)
{
    if (Value.Len() != 32) return false;
    for (TCHAR C : Value) if (!((C >= '0' && C <= '9') || (C >= 'a' && C <= 'f'))) return false;
    return true;
}

double UtcSeconds()
{
    const FDateTime Now = FDateTime::UtcNow();
    return static_cast<double>(Now.ToUnixTimestamp()) + Now.GetMillisecond() / 1000.0;
}

bool IntegerField(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, int64& Value)
{
    const TSharedPtr<FJsonValue>* Field = Object->Values.Find(Key);
    double Number = 0;
    if (!Field || (*Field)->Type != EJson::Number || !(*Field)->TryGetNumber(Number) ||
        !FMath::IsFinite(Number) || Number < 0 || Number > 9007199254740991.0 ||
        FMath::FloorToDouble(Number) != Number) return false;
    Value = static_cast<int64>(Number);
    return true;
}

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

UStaticMeshComponent* AWksimVisualGameMode::AddPart(AActor* ModelActor, const FString& Name, const TCHAR* Asset,
    const FVector& Location, const FVector& Scale, const FRotator& Rotation)
{
    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, Asset);
    if (!Mesh)
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM_MODEL required mesh missing: %s"), Asset);
        FPlatformMisc::RequestExitWithStatus(true, 22);
        return nullptr;
    }
    UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(ModelActor, *Name);
    Part->SetStaticMesh(Mesh);
    Part->SetMobility(EComponentMobility::Movable);
    Part->SetupAttachment(ModelActor->GetRootComponent());
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
        !(VehicleId == TEXT("1") || VehicleId == TEXT("px4") || VehicleId == TEXT("arducopter") || VehicleId == TEXT("joint")) || Port < 1024 || Port > 65535)
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
        if (!((VehicleId == TEXT("1") || VehicleId == TEXT("joint")) ? ProductChar : LegacyChar))
        {
            UE_LOG(LogTemp, Error, TEXT("WKSIM invalid run identity characters"));
            FPlatformMisc::RequestExitWithStatus(true, 20);
            return;
        }
    }
    if (VehicleId == TEXT("joint") &&
        (!FParse::Value(FCommandLine::Get(), TEXT("WksimInstance="), InstanceId) || !IsHexIdentity(InstanceId)))
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM invalid joint manager identity"));
        FPlatformMisc::RequestExitWithStatus(true, 20);
        return;
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
    const int32 ModelCount = VehicleId == TEXT("joint") ? 2 : 1;
    if (ModelCount == 2) JointVehicles.SetNum(2);
    for (int32 ModelIndex = 0; ModelIndex < ModelCount; ++ModelIndex)
    {
        AActor* Model = GetWorld()->SpawnActor<AActor>();
        if (ModelIndex == 0) Vehicle = Model;
        USceneComponent* Root = NewObject<USceneComponent>(Model, TEXT("AuthoritativePose"));
        Model->SetRootComponent(Root);
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
        UStaticMeshComponent* Body = AddPart(Model, TEXT("P450Body"), TEXT("/Game/Wksim/P450/SM_p450.SM_p450"), GeometryOffset, FVector::OneVector);
        if (!Body) return;
        Body->SetMaterial(0, BodyMaterial);
        const FVector Motors[] = {FVector(14.65, 14.7, 15.1), FVector(-14.65, -14.7, 15.1),
                                 FVector(14.65, -14.7, 15.1), FVector(-14.65, 14.7, 15.1)};
        const TCHAR* MotorNames[] = {TEXT("FR"), TEXT("RL"), TEXT("FL"), TEXT("RR")};
        for (int32 Index = 0; Index < 4; ++Index)
        {
            UStaticMeshComponent* Rotor = AddPart(Model, FString::Printf(TEXT("P450Rotor_%s"), MotorNames[Index]),
                Index < 2 ? TEXT("/Game/Wksim/P450/SM_p450_ccw.SM_p450_ccw") : TEXT("/Game/Wksim/P450/SM_p450_cw.SM_p450_cw"),
                Motors[Index] + GeometryOffset, FVector::OneVector);
            if (!Rotor) return;
            Rotor->SetMaterial(0, RotorMaterial);
            if (VehicleId == TEXT("joint")) JointVehicles[ModelIndex].Rotors.Add(Rotor);
            else { Rotors.Add(Rotor); RotorRpm.Add(0.0); }
            UE_LOG(LogTemp, Display, TEXT("WKSIM_MODEL rotor=%s source_sdf_index=%d origin_cm=%s yaw_sign=%d"),
                MotorNames[Index], Index, *Rotor->GetRelativeLocation().ToString(), Index < 2 ? -1 : 1);
        }
        if (VehicleId == TEXT("joint"))
        {
            JointVehicles[ModelIndex].Actor = Model;
            Model->SetActorHiddenInGame(true);
        }
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
    FString RgbPath;
    if (FParse::Value(FCommandLine::Get(), TEXT("WksimRgbConfig="), RgbPath) &&
        (VehicleId != TEXT("joint") || !LoadRgbConfig(RgbPath)))
    {
        UE_LOG(LogTemp, Error, TEXT("WKSIM invalid RGB configuration; joint source required"));
        FPlatformMisc::RequestExitWithStatus(true, 23);
        return;
    }
    int32 FixtureCase;
    if (FParse::Value(FCommandLine::Get(), TEXT("WksimRgbFixtureCase="), FixtureCase))
    {
        FString ManifestPath, Error;
        if (!RgbSensor || !FParse::Value(FCommandLine::Get(), TEXT("WksimRgbFixtureManifest="), ManifestPath))
        { FPlatformMisc::RequestExitWithStatus(true, 24); return; }
        RgbFixture = GetWorld()->SpawnActor<AWksimRgbFixture>();
        if (!RgbFixture->Configure(FixtureCase, Error) || !RgbFixture->WriteManifest(ManifestPath))
        { UE_LOG(LogTemp, Error, TEXT("WKSIM_RGB_FIXTURE %s"), *Error); FPlatformMisc::RequestExitWithStatus(true, 24); return; }
        // The fixture has its own known visual occlusion scene. Never use it
        // as proof of terrain/collision physics in the decorative city map.
        for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It) It->SetActorHiddenInGame(true);
    }
    UE_LOG(LogTemp, Display, TEXT("WKSIM_STARTING run=%s vehicle=%s port=%d world=%s"),
        *RunId, *VehicleId, Port, *GetWorld()->GetMapName());
}

bool AWksimVisualGameMode::ApplyPacket(const uint8* Bytes, int32 Count, FString& Ack)
{
    const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes), Count);
    TSharedPtr<FJsonObject> Object;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FString(Text.Length(), Text.Get())), Object) || !Object) return false;
    if (VehicleId == TEXT("joint"))
    {
        FString Kind;
        if (Object->TryGetStringField(TEXT("kind"), Kind) && Kind == TEXT("rgb_stream_control"))
        {
            FString Run, Instance, Epoch, Stream, NextStream;
            int64 Version, Generation, Request;
            bool Enabled;
            if (!RgbSensor || Object->Values.Num() != 10 ||
                !IntegerField(Object, TEXT("version"), Version) || Version != 3 ||
                !Object->TryGetStringField(TEXT("run_id"), Run) || Run != RunId ||
                !Object->TryGetStringField(TEXT("instance_id"), Instance) || Instance != InstanceId ||
                !Object->TryGetStringField(TEXT("epoch"), Epoch) || Epoch != JointEpoch ||
                !IntegerField(Object, TEXT("generation"), Generation) || Generation != JointGeneration || Generation < 1 ||
                !IntegerField(Object, TEXT("request_sequence"), Request) || Request <= LastRgbRequest ||
                !Object->TryGetStringField(TEXT("stream_id"), Stream) || Stream != RgbConfig.StreamId ||
                !Object->TryGetStringField(TEXT("next_stream_id"), NextStream) || !IsHexIdentity(NextStream) ||
                !Object->TryGetBoolField(TEXT("enabled"), Enabled) || Enabled == bRgbEnabled ||
                (Enabled ? NextStream == Stream : NextStream != Stream)) return false;
            // This changes capture only. There is no physics/flight command path.
            RgbSensor->Invalidate();
            RgbEpoch.Reset();
            bRgbEnabled = Enabled;
            LastRgbRequest = Request;
            if (Enabled) { RgbConfig.StreamId = NextStream; RgbLastStep = JointStep; }
            Object->SetStringField(TEXT("kind"), TEXT("rgb_stream_controlled"));
            FJsonSerializer::Serialize(Object.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Ack));
            return true;
        }
        if (Object->TryGetStringField(TEXT("kind"), Kind) && Kind == TEXT("joint_view_select"))
        {
            FString Run, Instance, Epoch;
            int64 Version, Generation, Request, Id;
            if (Object->Values.Num() != 8 || !IntegerField(Object, TEXT("version"), Version) || Version != 3 ||
                !Object->TryGetStringField(TEXT("run_id"), Run) || Run != RunId ||
                !Object->TryGetStringField(TEXT("instance_id"), Instance) || Instance != InstanceId ||
                !Object->TryGetStringField(TEXT("epoch"), Epoch) || Epoch != JointEpoch ||
                !IntegerField(Object, TEXT("generation"), Generation) || Generation < 1 || Generation != JointGeneration ||
                !IntegerField(Object, TEXT("request_sequence"), Request) || Request <= LastViewRequest ||
                !IntegerField(Object, TEXT("vehicle_id"), Id) || Id < 1 || Id > 2) return false;
            SelectedVehicleId = static_cast<int32>(Id);
            LastViewRequest = Request;
            Ack = FString::Printf(TEXT("{\"version\":3,\"kind\":\"joint_view_selected\",\"run_id\":\"%s\",\"instance_id\":\"%s\","
                "\"epoch\":\"%s\",\"generation\":%lld,\"request_sequence\":%lld,\"vehicle_id\":%lld}"),
                *RunId, *InstanceId, *JointEpoch, JointGeneration, Request, Id);
            return true;
        }
        return ApplyJointPacket(Object, Ack);
    }
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

bool AWksimVisualGameMode::ApplyJointPacket(const TSharedPtr<FJsonObject>& Object, FString& Ack)
{
    // Validate the complete datagram before changing either Actor or acceptance guards.
    int64 Version, Generation, Sequence, Step, SimTimeNs;
    FString Run, Instance, Epoch, Kind, Phase, DisplayClock;
    double Wall = 0, DisplayWall = 0, AgeBound = 0;
    if (Object->Values.Num() != 22 || !IntegerField(Object, TEXT("version"), Version) || Version != 3 ||
        !Object->TryGetStringField(TEXT("kind"), Kind) || Kind != TEXT("joint_state") ||
        !Object->TryGetStringField(TEXT("run_id"), Run) || Run != RunId ||
        !Object->TryGetStringField(TEXT("instance_id"), Instance) || Instance != InstanceId ||
        !Object->TryGetStringField(TEXT("epoch"), Epoch) || !IsHexIdentity(Epoch) ||
        !IntegerField(Object, TEXT("generation"), Generation) || Generation < 1 || Generation < JointGeneration ||
        !IntegerField(Object, TEXT("sequence"), Sequence) ||
        !IntegerField(Object, TEXT("step"), Step) ||
        !IntegerField(Object, TEXT("sim_time_ns"), SimTimeNs) || Step > 9007199254LL || SimTimeNs != Step * 1000000LL ||
        !Object->TryGetStringField(TEXT("phase"), Phase) ||
        !(Phase == TEXT("running") || Phase == TEXT("paused") || Phase == TEXT("faulted") || Phase == TEXT("stopped")) ||
        !Object->TryGetNumberField(TEXT("source_wall_time_s"), Wall) || !FMath::IsFinite(Wall) || Wall < 0 ||
        !Object->TryGetStringField(TEXT("display_clock"), DisplayClock) || DisplayClock != TEXT("windows_utc_bound") ||
        !Object->TryGetNumberField(TEXT("display_wall_time_s"), DisplayWall) || !FMath::IsFinite(DisplayWall) ||
        !Object->TryGetNumberField(TEXT("transport_age_bound_s"), AgeBound) || !FMath::IsFinite(AgeBound) ||
        AgeBound < 0 || AgeBound > 0.75 || UtcSeconds() - DisplayWall > 0.75 || UtcSeconds() - DisplayWall < -0.25) return false;
    const bool NewGeneration = Generation > JointGeneration;
    if ((!NewGeneration && (Epoch != JointEpoch || Sequence <= LastSequence || Step < JointStep)) ||
        (NewGeneration && Epoch == JointEpoch)) return false;
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
    const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
    if (!Object->TryGetArrayField(TEXT("vehicles"), Items) || Items->Num() < 1 || Items->Num() > 2 ||
        (NewGeneration && Items->Num() != 2)) return false;
    struct FValidatedVehicle { int32 Index; TArray<double> P, Q, Rpm; };
    TArray<FValidatedVehicle> Validated;
    bool Seen[2] = {false, false};
    for (const auto& Item : *Items)
    {
        if (Item->Type != EJson::Object) return false;
        const TSharedPtr<FJsonObject> State = Item->AsObject();
        int64 Id;
        FString Stack;
        double ModelTime;
        FValidatedVehicle Value;
        if (State->Values.Num() != 6 || !IntegerField(State, TEXT("vehicle_id"), Id) || Id < 1 || Id > 2 || Seen[Id - 1] ||
            !State->TryGetStringField(TEXT("stack"), Stack) || Stack != (Id == 1 ? TEXT("arducopter") : TEXT("px4")) ||
            !State->TryGetNumberField(TEXT("model_time_s"), ModelTime) || !FMath::IsFinite(ModelTime) || ModelTime < 0 ||
            FMath::Abs(ModelTime - Step / 1000.0) > 1e-8 ||
            !VectorField(State, TEXT("position_ned_m"), 3, Value.P) ||
            !VectorField(State, TEXT("quaternion_wxyz"), 4, Value.Q) ||
            !VectorField(State, TEXT("rotor_rpm"), 4, Value.Rpm)) return false;
        // JSON numbers only; legacy parsing intentionally keeps its original behavior.
        for (const TCHAR* Key : {TEXT("position_ned_m"), TEXT("quaternion_wxyz"), TEXT("rotor_rpm")})
            for (const auto& Number : State->GetArrayField(Key)) if (Number->Type != EJson::Number) return false;
        if (State->Values[TEXT("model_time_s")]->Type != EJson::Number ||
            FMath::Abs(FQuat(Value.Q[1], Value.Q[2], Value.Q[3], Value.Q[0]).SizeSquared() - 1.0) > 1e-5 ||
            FMath::Max3(FMath::Abs(Value.P[0]), FMath::Abs(Value.P[1]), FMath::Abs(Value.P[2])) > 1000000.0) return false;
        for (double Rpm : Value.Rpm) if (Rpm < 0 || Rpm > 100000) return false;
        Value.Index = static_cast<int32>(Id - 1);
        Seen[Value.Index] = true;
        Validated.Add(MoveTemp(Value));
    }
    if (Object->Values[TEXT("source_wall_time_s")]->Type != EJson::Number ||
        Object->Values[TEXT("display_wall_time_s")]->Type != EJson::Number ||
        Object->Values[TEXT("transport_age_bound_s")]->Type != EJson::Number) return false;
    if (NewGeneration)
    {
        if (RgbSensor) RgbSensor->Invalidate();
        RgbEpoch.Reset();
        RgbLastStep = -1;
        for (auto& State : JointVehicles)
        {
            State.Step = -1;
            State.ReceivedWall = 0;
            State.SourceWall = 0;
            State.PositionNed = FVector::ZeroVector;
            State.Phase.Reset();
            State.Actor->SetActorHiddenInGame(true);
            for (auto& Rotor : State.Rotors) Rotor->SetRelativeRotation(FRotator::ZeroRotator);
        }
    }
    TArray<TSharedPtr<FJsonValue>> Applied;
    for (const auto& Value : Validated)
    {
        auto& State = JointVehicles[Value.Index];
        const double StepSeconds = State.Step < 0 ? 0.0 : (Step - State.Step) / 1000.0;
        for (int32 Index = 0; Index < 4; ++Index)
            State.Rotors[Index]->AddLocalRotation(FRotator(0,
                FMath::Fmod(Value.Rpm[Index] * 6.0 * StepSeconds * (Index < 2 ? -1 : 1), 360.0), 0));
        State.PositionNed = FVector(Value.P[0], Value.P[1], Value.P[2]);
        State.Actor->SetActorLocationAndRotation(FVector(Value.P[0] * 100, Value.P[1] * 100, -Value.P[2] * 100),
            FQuat(-Value.Q[1], -Value.Q[2], Value.Q[3], Value.Q[0]), false, nullptr, ETeleportType::TeleportPhysics);
        State.Actor->SetActorHiddenInGame(false);
        State.Step = Step;
        State.Phase = Phase;
        State.ReceivedWall = FPlatformTime::Seconds();
        State.SourceWall = DisplayWall;
        const FVector P = State.Actor->GetActorLocation();
        const FQuat Q = State.Actor->GetActorQuat();
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetNumberField(TEXT("vehicle_id"), Value.Index + 1);
        auto Numbers = [](std::initializer_list<double> ValuesToEncode)
        {
            TArray<TSharedPtr<FJsonValue>> Result;
            for (double Number : ValuesToEncode) Result.Add(MakeShared<FJsonValueNumber>(Number));
            return Result;
        };
        Entry->SetArrayField(TEXT("ue_position_cm"), Numbers({P.X, P.Y, P.Z}));
        Entry->SetArrayField(TEXT("ue_quaternion_xyzw"), Numbers({Q.X, Q.Y, Q.Z, Q.W}));
        Entry->SetArrayField(TEXT("rotor_rpm"), Numbers({Value.Rpm[0], Value.Rpm[1], Value.Rpm[2], Value.Rpm[3]}));
        Entry->SetArrayField(TEXT("rotor_yaw_deg"), Numbers({State.Rotors[0]->GetRelativeRotation().Yaw,
            State.Rotors[1]->GetRelativeRotation().Yaw, State.Rotors[2]->GetRelativeRotation().Yaw,
            State.Rotors[3]->GetRelativeRotation().Yaw}));
        Applied.Add(MakeShared<FJsonValueObject>(Entry));
    }
    JointGeneration = Generation;
    JointEpoch = Epoch;
    JointStep = Step;
    LastSequence = Sequence;
    SourceTime = Step / 1000.0;
    auto Reply = MakeShared<FJsonObject>();
    Reply->SetNumberField(TEXT("version"), 3);
    Reply->SetStringField(TEXT("kind"), TEXT("joint_actor"));
    Reply->SetStringField(TEXT("run_id"), RunId);
    Reply->SetStringField(TEXT("instance_id"), InstanceId);
    Reply->SetStringField(TEXT("epoch"), Epoch);
    Reply->SetNumberField(TEXT("generation"), Generation);
    Reply->SetNumberField(TEXT("sequence"), Sequence);
    Reply->SetNumberField(TEXT("step"), Step);
    Reply->SetNumberField(TEXT("sim_time_ns"), SimTimeNs);
    Reply->SetNumberField(TEXT("selected_vehicle_id"), SelectedVehicleId);
    Reply->SetArrayField(TEXT("vehicles"), Applied);
    TArray<TSharedPtr<FJsonValue>> Observed;
    for (int32 Index = 0; Index < JointVehicles.Num(); ++Index)
    {
        const auto& State = JointVehicles[Index];
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetNumberField(TEXT("vehicle_id"), Index + 1);
        Entry->SetNumberField(TEXT("step"), State.Step);
        Entry->SetBoolField(TEXT("stale"), IsJointStale(Index));
        Entry->SetBoolField(TEXT("visible"), !State.Actor->IsHidden());
        Observed.Add(MakeShared<FJsonValueObject>(Entry));
    }
    Reply->SetArrayField(TEXT("observed_vehicles"), Observed);
    const FVector CameraPosition = Camera->GetActorLocation();
    TArray<TSharedPtr<FJsonValue>> CameraValues;
    for (double Number : {CameraPosition.X, CameraPosition.Y, CameraPosition.Z}) CameraValues.Add(MakeShared<FJsonValueNumber>(Number));
    Reply->SetArrayField(TEXT("camera_position_cm"), CameraValues);
    FJsonSerializer::Serialize(Reply, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Ack));
    return true;
}

bool AWksimVisualGameMode::IsJointStale(int32 Index) const
{
    if (!JointVehicles.IsValidIndex(Index)) return true;
    const auto& State = JointVehicles[Index];
    const double Age = UtcSeconds() - State.SourceWall;
    return State.Step < 0 || FPlatformTime::Seconds() - State.ReceivedWall > 0.75 || Age > 0.75 || Age < -0.25;
}

bool AWksimVisualGameMode::IsStale() const
{
    if (VehicleId == TEXT("joint")) return IsJointStale(0) || IsJointStale(1);
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
        uint8 Buffer[8192];
        int32 Count = 0;
        auto Sender = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
        if (!Socket->RecvFrom(Buffer, sizeof(Buffer), Count, *Sender) || Count <= 0) break;
        FString Ack;
        if (Pending > (VehicleId == TEXT("joint") ? sizeof(Buffer) : 4096) || Sender->ToString(false) != TEXT("127.0.0.1") || !ApplyPacket(Buffer, Count, Ack))
        {
            ++Rejected;
            continue;
        }
        const FTCHARToUTF8 Encoded(*Ack);
        int32 Sent = 0;
        Socket->SendTo(reinterpret_cast<const uint8*>(Encoded.Get()), Encoded.Length(), Sent, *Sender);
    }
    if (VehicleId != TEXT("joint") && !IsStale())
    {
        for (int32 Index = 0; Index < Rotors.Num(); ++Index)
            Rotors[Index]->AddLocalRotation(FRotator(0, RotorRpm[Index] * 6.0 * DeltaSeconds * (Index < 2 ? -1 : 1), 0));
    }
    if (VehicleId == TEXT("joint"))
    {
        if (auto* Controller = GetWorld()->GetFirstPlayerController())
        {
            if (Controller->WasInputKeyJustPressed(EKeys::One)) SelectedVehicleId = 1;
            if (Controller->WasInputKeyJustPressed(EKeys::Two)) SelectedVehicleId = 2;
            if (Controller->WasInputKeyJustPressed(EKeys::Tab)) SelectedVehicleId = 3 - SelectedVehicleId;
        }
    }
    const AActor* Follow = VehicleId == TEXT("joint") ? JointVehicles[SelectedVehicleId - 1].Actor.Get() : Vehicle.Get();
    const FVector Focus = Follow->GetActorLocation() + FVector(0, 0, 20);
    Camera->SetActorLocation(Focus + FVector(-260, -300, 120));
    Camera->SetActorRotation((Focus - Camera->GetActorLocation()).Rotation());
    const double Wall = FPlatformTime::Seconds();
    // Poll only; never wait on the render thread or connect it to the physics clock.
    // The startup signal means assets compiled + initial render submission drained,
    // not sensor calibration or assurance about every later visual frame.
    if (!bRenderReady)
    {
        if (FAssetCompilingManager::Get().GetNumRemainingAssets() > 0 || (RgbFixture && !RgbFixture->IsReady()))
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
    TickRgb();
}

bool AWksimVisualGameMode::LoadRgbConfig(const FString& Path)
{
    FString Text;
    TSharedPtr<FJsonObject> Object;
    if (FPaths::IsRelative(Path) || IFileManager::Get().FileSize(*Path) > 16384 ||
        !FFileHelper::LoadFileToString(Text, *Path) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Object) || !Object.IsValid()) return false;
    int64 Version, Id, Width, Height, Interval, Notify;
    double Fov;
    TArray<double> P, Q;
    if (Object->Values.Num() != 12 || !IntegerField(Object, TEXT("version"), Version) || Version != 1 ||
        !IntegerField(Object, TEXT("vehicle_id"), Id) || Id < 1 || Id > 2 ||
        !IntegerField(Object, TEXT("width"), Width) || Width < 16 || Width > 4096 ||
        !IntegerField(Object, TEXT("height"), Height) || Height < 16 || Height > 4096 || Width * Height > 4194304 ||
        !IntegerField(Object, TEXT("interval_steps"), Interval) || Interval < 1 || Interval > 60000 ||
        !IntegerField(Object, TEXT("notify_port"), Notify) || Notify < 1024 || Notify > 65535 || Notify == LaunchPort ||
        !Object->TryGetNumberField(TEXT("horizontal_fov_degrees"), Fov) || !FMath::IsFinite(Fov) || Fov < 5 || Fov > 150 ||
        !Object->TryGetStringField(TEXT("sensor_id"), RgbConfig.SensorId) ||
        !Object->TryGetStringField(TEXT("stream_id"), RgbConfig.StreamId) || !IsHexIdentity(RgbConfig.StreamId) ||
        !Object->TryGetStringField(TEXT("output_directory"), RgbConfig.OutputDirectory) ||
        !VectorField(Object, TEXT("position_cm"), 3, P) || !VectorField(Object, TEXT("quaternion_xyzw"), 4, Q)) return false;
    for (const TCHAR* Key : {TEXT("position_cm"), TEXT("quaternion_xyzw")})
        for (const auto& Item : Object->GetArrayField(Key)) if (Item->Type != EJson::Number) return false;
    if (Object->Values[TEXT("horizontal_fov_degrees")]->Type != EJson::Number) return false;
    RgbConfig.RunId = RunId;
    RgbConfig.InstanceId = InstanceId;
    // Validate before starting; the first accepted source epoch replaces this value.
    RgbConfig.Epoch = TEXT("pending");
    RgbConfig.VehicleId = LexToString(Id);
    RgbConfig.Width = static_cast<int32>(Width);
    RgbConfig.Height = static_cast<int32>(Height);
    RgbConfig.HorizontalFovDegrees = static_cast<float>(Fov);
    RgbConfig.CameraInVehicle = FTransform(FQuat(Q[0], Q[1], Q[2], Q[3]), FVector(P[0], P[1], P[2]));
    RgbIntervalSteps = Interval;
    RgbNotifyPort = static_cast<int32>(Notify);
    RgbSensor = NewObject<UWksimRgbSensor>(this);
    RgbSensor->RegisterComponent();
    FString Error;
    if (!RgbSensor->Configure(RgbConfig, Error))
    { UE_LOG(LogTemp, Error, TEXT("WKSIM_RGB config rejected: %s"), *Error); return false; }
    RgbSensor->Invalidate();
    return true;
}

void AWksimVisualGameMode::TickRgb()
{
    if (!RgbSensor) return;
    // Every moving Actor must represent this exact authoritative joint step.
    // Partial/outdated display data cannot be relabelled as a synchronous image.
    const bool Current = bRgbEnabled && bRenderReady && !IsStale() && JointVehicles.Num() == 2 &&
        JointVehicles[0].Step == JointStep && JointVehicles[1].Step == JointStep &&
        JointVehicles[0].Phase != TEXT("stopped") && JointVehicles[1].Phase != TEXT("stopped");
    if (!Current)
    {
        RgbSensor->Invalidate();
        RgbEpoch.Reset();
    }
    FString Completed, Error;
    if (RgbSensor->Poll(Completed, Error))
    {
        auto Event = MakeShared<FJsonObject>();
        Event->SetStringField(TEXT("schema"), TEXT("wksim.rgb-ready.v2"));
        Event->SetStringField(TEXT("run_id"), RunId);
        Event->SetStringField(TEXT("instance_id"), InstanceId);
        Event->SetStringField(TEXT("epoch"), JointEpoch);
        Event->SetStringField(TEXT("stream_id"), RgbConfig.StreamId);
        Event->SetNumberField(TEXT("generation"), JointGeneration);
        Event->SetStringField(TEXT("metadata"), FPaths::GetCleanFilename(Completed));
        FString Json;
        FJsonSerializer::Serialize(Event, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json));
        const FTCHARToUTF8 Bytes(*Json);
        const auto Destination = FIPv4Endpoint(FIPv4Address::InternalLoopback, static_cast<uint16>(RgbNotifyPort)).ToInternetAddr();
        int32 Sent;
        Socket->SendTo(reinterpret_cast<const uint8*>(Bytes.Get()), Bytes.Length(), Sent, *Destination);
        UE_LOG(LogTemp, Display, TEXT("WKSIM_RGB_READY %s generation=%lld"), *Completed, JointGeneration);
    }
    if (!Error.IsEmpty()) UE_LOG(LogTemp, Warning, TEXT("WKSIM_RGB %s"), *Error);
    if (!Current || RgbSensor->IsBusy() || JointStep <= RgbLastStep ||
        (RgbLastStep >= 0 && JointStep - RgbLastStep < RgbIntervalSteps)) return;
    if (RgbEpoch != JointEpoch)
    {
        RgbConfig.Epoch = JointEpoch;
        if (!RgbSensor->Configure(RgbConfig, Error))
        { UE_LOG(LogTemp, Warning, TEXT("WKSIM_RGB %s"), *Error); return; }
        RgbEpoch = JointEpoch;
    }
    const int32 Index = FCString::Atoi(*RgbConfig.VehicleId) - 1;
    FWksimRgbRequest Request;
    Request.RunId = RunId;
    Request.InstanceId = InstanceId;
    Request.Epoch = JointEpoch;
    Request.StreamId = RgbConfig.StreamId;
    Request.Step = JointStep;
    Request.SimTimeSeconds = SourceTime;
    Request.CameraWorldPose = RgbConfig.CameraInVehicle * JointVehicles[Index].Actor->GetActorTransform();
    if (RgbSensor->RequestCapture(Request, Error)) RgbLastStep = JointStep;
    else if (!Error.IsEmpty()) UE_LOG(LogTemp, Warning, TEXT("WKSIM_RGB %s"), *Error);
}

void AWksimVisualGameMode::EndPlay(const EEndPlayReason::Type Reason)
{
    if (RgbSensor) RgbSensor->Invalidate();
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
    if (Mode->VehicleId == TEXT("joint"))
    {
        DrawRect(FLinearColor(0.025, 0.04, 0.065, .88), 20, 20, 750, 200);
        DrawText(TEXT("WKSIM | AP + PX4 JOINT | UE 5.5 | VIEW ONLY"), FLinearColor::White, 34, 30, GEngine->GetMediumFont(), 1.1);
        DrawText(FString::Printf(TEXT("1 / 2 / Tab: follow %s | Generation %lld | %s"),
            Mode->SelectedVehicleId == 1 ? TEXT("AP #1") : TEXT("PX4 #2"), Mode->JointGeneration,
            Mode->IsRenderReady() ? TEXT("DISPLAY READY") : TEXT("PREPARING DISPLAY")), FLinearColor(.65, .75, .9), 34, 62);
        for (int32 Index = 0; Index < Mode->JointVehicles.Num(); ++Index)
        {
            const auto& State = Mode->JointVehicles[Index];
            const bool Stale = Mode->IsJointStale(Index);
            const FString Status = State.Step < 0 ? TEXT("WAITING") : (Stale ? TEXT("STALE") : State.Phase.ToUpper());
            DrawText(FString::Printf(TEXT("%s %s #%d | %s | Step %lld"),
                Mode->SelectedVehicleId == Index + 1 ? TEXT(">") : TEXT(" "),
                Index == 0 ? TEXT("AP") : TEXT("PX4"), Index + 1, *Status, State.Step),
                Stale ? FLinearColor(1, .4, .25) : FLinearColor(.2, 1, .5), 34, 90 + Index * 48);
            DrawText(FString::Printf(TEXT("N %.3f  E %.3f  D %.3f m"), State.PositionNed.X, State.PositionNed.Y, State.PositionNed.Z),
                FLinearColor::White, 48, 111 + Index * 48);
        }
        DrawText(TEXT("True shared coordinates: vehicles may overlap | P450 visual / quad-X physics"), FLinearColor(.65, .75, .9), 34, 192);
        return;
    }
    const FLinearColor StatusColor = Mode->IsStale() ? FLinearColor(1, .25, .15) : FLinearColor(.2, 1, .5);
    DrawRect(FLinearColor(0.025, 0.04, 0.065, .88), 20, 20, 610, 132);
    DrawText(FString::Printf(TEXT("WKSIM  |  %s  |  UE 5.5  |  VIEW ONLY"), *Mode->VehicleId), FLinearColor::White, 34, 30, GEngine->GetMediumFont(), 1.1);
    DrawText(!Mode->IsRenderReady() ? TEXT("PREPARING DISPLAY / state processing independent") :
        (Mode->IsStale() ? TEXT("STALE / waiting for authoritative state") : TEXT("LIVE / independent SITL physics")), StatusColor, 34, 64);
    DrawText(FString::Printf(TEXT("N %.3f  E %.3f  D %.3f m     SIM %.3f s"),
        Mode->PositionNed.X, Mode->PositionNed.Y, Mode->PositionNed.Z, Mode->SourceTime), FLinearColor::White, 34, 91);
    DrawText(FString::Printf(TEXT("Sequence %lld   Rejected %lld   P450 visual / quad-X physics"), Mode->LastSequence, Mode->Rejected), FLinearColor(.65, .75, .9), 34, 118);
}
