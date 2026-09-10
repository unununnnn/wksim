#include "WksimRgbFixture.h"
#include "WksimRgbSensor.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonSerializer.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace
{
int ModuleIdentityAnchor;
// OpenCV 4.12.0 DICT_6X6_250 ID 23, 8x8 including one black border cell.
const TCHAR* ArUcoBits = TEXT("0000000001001100010010100001111000110010011001100110011000000000");
TArray<TSharedPtr<FJsonValue>> VectorJson(const FVector& V)
{
    return {MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)};
}
}

bool AWksimRgbFixture::Configure(int32 Case, FString& Error)
{
    if (CaseId != -1 || Case < 0 || Case > 5) { Error = TEXT("Fixture case must be 0..5 and configured once"); return false; }
    if (Case == 4) return ConfigureArUco(Error);
    if (Case == 5)
    {
        // Flight candidate: same marker geometry as case 4, but the actor keeps
        // its spawn transform until the first real capture request solves the
        // SceneAnchor from the actual camera pose. Capture starts disabled.
        if (!BuildArUcoGeometry(Error)) return false;
        CaseId = 5; return true;
    }
#if WITH_EDITOR
    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Cube) { Error = TEXT("Engine cube unavailable"); return false; }
    USceneComponent* Root = NewObject<USceneComponent>(this, TEXT("CalibrationRoot"));
    SetRootComponent(Root); Root->RegisterComponent();
    const FVector Positions[] = {FVector(425, 0, 100), FVector(400, 0, 100), FVector(350, 0, 100)};
    const FVector Sizes[] = {FVector(1, 230, 230), FVector(1, 160, 160), FVector(1, 40, 180)};
    const FLinearColor Colors[] = {FLinearColor::Blue, FLinearColor::Red, FLinearColor::Green};
    const TCHAR* Names[] = {TEXT("BlueBackground"), TEXT("RedTarget"), TEXT("GreenOccluder")};
    const FVector MeshSize = Cube->GetBoundingBox().GetSize();
    if (MeshSize.GetMin() <= 0) { Error = TEXT("Invalid engine cube bounds"); return false; }
    for (int32 Index = 0; Index < 3; ++Index)
    {
        UMaterial* Material = NewObject<UMaterial>(this, NAME_None, RF_Transient);
        Material->SetShadingModel(MSM_Unlit);
        auto* Color = NewObject<UMaterialExpressionConstant3Vector>(Material, NAME_None, RF_Transient);
        Color->Constant = Colors[Index];
        Color->Material = Material;
        Material->GetExpressionCollection().AddExpression(Color);
        Material->GetEditorOnlyData()->EmissiveColor.Expression = Color;
        Material->PostEditChange();
        Materials.Add(Material);
        UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this, Names[Index]);
        Part->SetStaticMesh(Cube);
        Part->SetMaterial(0, Material);
        Part->SetupAttachment(Root);
        Part->SetRelativeLocation(Positions[Index]);
        Part->SetRelativeScale3D(Sizes[Index] / MeshSize);
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Part->SetSimulatePhysics(false);
        Part->SetCastShadow(false);
        Part->SetVisibility(Index != 2 || Case == 2);
        Part->RegisterComponent();
        Parts.Add(Part);
    }
    CaseId = Case;
    return true;
#else
    Error = TEXT("Calibration fixture requires the installed editor material compiler");
    return false;
#endif
}

bool AWksimRgbFixture::IsReady() const
{
    if (CaseId < 0 || Parts.Num() != (IsArUco() ? 66 : 3) || Materials.Num() != (IsArUco() ? 2 : 3)) return false;
    for (const UMaterial* Material : Materials) if (Material->IsCompiling()) return false;
    return true;
}

bool AWksimRgbFixture::ConfigureArUco(FString& Error)
{
    if (!BuildArUcoGeometry(Error)) return false;
    CaseId = 4; return true;
}

bool AWksimRgbFixture::BuildArUcoGeometry(FString& Error)
{
#if WITH_EDITOR
    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!Cube || Cube->GetBoundingBox().GetSize().GetMin() <= 0)
    { Error = TEXT("Engine cube unavailable or invalid"); return false; }
    USceneComponent* Root = NewObject<USceneComponent>(this, TEXT("ArUcoCalibrationRoot"));
    SetRootComponent(Root); Root->RegisterComponent();
    for (int32 Index = 0; Index < 2; ++Index)
    {
        UMaterial* Material = NewObject<UMaterial>(this, Index ? TEXT("M_ArUco23_White") : TEXT("M_ArUco23_Black"), RF_Transient);
        Material->SetShadingModel(MSM_Unlit);
        auto* Color = NewObject<UMaterialExpressionConstant3Vector>(Material, NAME_None, RF_Transient);
        Color->Constant = Index ? FLinearColor::White : FLinearColor::Black;
        Color->Material = Material;
        Material->GetExpressionCollection().AddExpression(Color);
        Material->GetEditorOnlyData()->EmissiveColor.Expression = Color;
        Material->PostEditChange(); Materials.Add(Material);
    }
    const auto AddPart = [&](FString Name, FVector Position, FVector Size, int32 Color)
    {
        auto* Part = NewObject<UStaticMeshComponent>(this, FName(*Name));
        Part->SetStaticMesh(Cube); Part->SetMaterial(0, Materials[Color]);
        Part->SetupAttachment(Root); Part->SetRelativeLocation(Position);
        Part->SetRelativeScale3D(Size / Cube->GetBoundingBox().GetSize());
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision); Part->SetSimulatePhysics(false);
        Part->SetCastShadow(false); Part->RegisterComponent(); Parts.Add(Part);
    };
    AddPart(TEXT("ArUcoWhiteMargin"), FVector(230.15,32,6), FVector(.1,62.5,62.5),1);
    for (int32 Row = 0; Row < 8; ++Row) for (int32 Column = 0; Column < 8; ++Column)
        AddPart(FString::Printf(TEXT("ArUcoCell_%d_%d"),Row,Column),
            FVector(230.05,32+(Column-3.5)*6.25,6+(3.5-Row)*6.25),
            FVector(.1,6.25,6.25), ArUcoBits[Row*8+Column] == '1' ? 1 : 0);
    AddPart(TEXT("ArUcoOccluder"),FVector(205.05,32,6),FVector(.1,100,100),1);
    Parts.Last()->SetVisibility(false);
    return true;
#else
    Error = TEXT("ArUco scene requires the installed editor material compiler"); return false;
#endif
}

bool AWksimRgbFixture::AdvanceArUco(const FWksimRgbRequest& Request, int64 Generation, const FString& Directory,
                                    const FTransform& CameraInVehicle)
{
    if (!IsArUco() || !IsReady() || Request.Step < 0 || Generation < 0) return false;
    if (SceneEpoch != Request.Epoch)
    {
        if (SceneGeneration >= 0 && Generation <= SceneGeneration) return false;
        SceneEpoch = Request.Epoch; SceneGeneration = Generation; SceneFirstStep = Request.Step; SceneStep = -1;
        SceneAnchorValid = false;
    }
    if (Generation != SceneGeneration || Request.Step <= SceneStep) return false;
    SceneStep = Request.Step;
    SceneRun = Request.RunId; SceneInstance = Request.InstanceId; SceneStream = Request.StreamId;
    SceneCamera = Request.CameraWorldPose;
    const int64 Elapsed = SceneStep - SceneFirstStep;
    if (IsFlightArUco())
    {
        if (!SceneAnchorValid)
        {
            // First actual capture request of this epoch (capture is enabled and
            // current; TickRgb gates otherwise): solve the initial vehicle
            // transform from the real camera world pose and the fixed mount.
            // CameraWorldPose = CameraInVehicle * VehicleTransform, so
            // VehicleTransform = CameraInVehicle^-1 * CameraWorldPose.
            SceneAnchor = CameraInVehicle.Inverse() * SceneCamera;
            SceneAnchor.SetScale3D(FVector::OneVector);
            SceneAnchorValid = true;
            SetActorTransform(SceneAnchor);
        }
        // Authority-step timeline (1ms steps; never wall clock or DeltaTime):
        // 0-2s static, 2-6s +Y at 0.25m/s (1m total), 6-8s fully occluded,
        // 8-12s recovered static, held thereafter.
        const double Offset = FMath::Clamp(static_cast<double>(Elapsed-2000),0.,4000.) * .025;
        SetActorLocation(SceneAnchor.GetLocation() + FVector(0,Offset,0));
        Parts.Last()->SetVisibility(Elapsed >= 6000 && Elapsed < 8000);
    }
    else
    {
        const double Offset = FMath::Clamp(static_cast<double>(Elapsed-1000),0.,1000.) * .025;
        SetActorLocation(FVector(0,Offset,0));
        Parts.Last()->SetVisibility(Elapsed >= 2000 && Elapsed < 3000);
    }
    // Saved before CaptureScene, on the same game thread. Only completed RGB
    // records with this exact identity/step admit a scene record to the audit.
    const FString Path = FPaths::Combine(Directory,FString::Printf(TEXT("aruco-%s-%lld.json"),*SceneEpoch,SceneStep));
    if (IFileManager::Get().FileExists(*Path)) return false;
    return WriteManifest(Path);
}

bool AWksimRgbFixture::WriteManifest(const FString& Path) const
{
    if (CaseId < 0) return false;
    auto Json = MakeShared<FJsonObject>();
    Json->SetStringField(TEXT("schema"), TEXT("wksim.rgb-calibration-visual.v1"));
    Json->SetNumberField(TEXT("case_id"), CaseId);
    if (IsArUco())
    {
        Json->SetStringField(TEXT("scene_schema"), TEXT("wksim.aruco-scene.v1"));
        Json->SetStringField(TEXT("dictionary"), TEXT("DICT_6X6_250"));
        Json->SetNumberField(TEXT("marker_id"),23);
        Json->SetStringField(TEXT("row_major_bits"),ArUcoBits);
        Json->SetStringField(TEXT("run_id"),SceneRun); Json->SetStringField(TEXT("instance_id"),SceneInstance);
        Json->SetStringField(TEXT("stream_id"),SceneStream); Json->SetStringField(TEXT("epoch"),SceneEpoch);
        Json->SetNumberField(TEXT("generation"),SceneGeneration);
        Json->SetNumberField(TEXT("first_step"),SceneFirstStep); Json->SetNumberField(TEXT("step"),SceneStep);
        Json->SetArrayField(TEXT("camera_position_cm"),VectorJson(SceneCamera.GetLocation()));
        const FQuat CameraQ = SceneCamera.GetRotation();
        Json->SetArrayField(TEXT("camera_quaternion_xyzw"),{MakeShared<FJsonValueNumber>(CameraQ.X),MakeShared<FJsonValueNumber>(CameraQ.Y),
            MakeShared<FJsonValueNumber>(CameraQ.Z),MakeShared<FJsonValueNumber>(CameraQ.W)});
        if (IsFlightArUco())
        {
            Json->SetNumberField(TEXT("scene_case"), 5);
            Json->SetBoolField(TEXT("anchor_valid"), SceneAnchorValid);
            if (SceneAnchorValid)
            {
                Json->SetArrayField(TEXT("anchor_position_cm"), VectorJson(SceneAnchor.GetLocation()));
                const FQuat AnchorQ = SceneAnchor.GetRotation();
                Json->SetArrayField(TEXT("anchor_quaternion_xyzw"),{MakeShared<FJsonValueNumber>(AnchorQ.X),
                    MakeShared<FJsonValueNumber>(AnchorQ.Y),MakeShared<FJsonValueNumber>(AnchorQ.Z),
                    MakeShared<FJsonValueNumber>(AnchorQ.W)});
            }
            // Phase boundaries in authority steps relative to first_step.
            const int64 Elapsed = SceneStep - SceneFirstStep;
            const TCHAR* Phase = TEXT("pending_enable");
            int64 PhaseStart = SceneFirstStep;
            if (SceneAnchorValid && Elapsed >= 0)
            {
                if (Elapsed < 2000) { Phase = TEXT("static_initial"); }
                else if (Elapsed < 6000) { Phase = TEXT("moving"); PhaseStart = SceneFirstStep + 2000; }
                else if (Elapsed < 8000) { Phase = TEXT("occluded"); PhaseStart = SceneFirstStep + 6000; }
                else if (Elapsed < 12000) { Phase = TEXT("recovered"); PhaseStart = SceneFirstStep + 8000; }
                else { Phase = TEXT("settled"); PhaseStart = SceneFirstStep + 12000; }
            }
            Json->SetStringField(TEXT("phase"), Phase);
            Json->SetNumberField(TEXT("phase_start_step"), PhaseStart);
        }
    }
#if PLATFORM_WINDOWS
    // Query the loaded image containing this module's data address, without
    // loading another DLL or changing its reference count.
    HMODULE Module = nullptr;
    WCHAR Filename[32768];
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
            reinterpret_cast<LPCWSTR>(&ModuleIdentityAnchor), &Module)) return false;
    const DWORD Length = GetModuleFileNameW(Module, Filename, UE_ARRAY_COUNT(Filename));
    if (Length == 0 || Length >= UE_ARRAY_COUNT(Filename)) return false;
    Json->SetStringField(TEXT("module_path"), FString(Filename));
    Json->SetNumberField(TEXT("process_id"), GetCurrentProcessId());
#endif
    Json->SetBoolField(TEXT("physics_authority"), false);
    Json->SetStringField(TEXT("coordinates"), TEXT("UE world centimeters; X forward Y right Z up"));
    TArray<TSharedPtr<FJsonValue>> Objects;
    for (const UStaticMeshComponent* Part : Parts)
    {
        auto Object = MakeShared<FJsonObject>();
        Object->SetStringField(TEXT("name"), Part->GetName());
        Object->SetBoolField(TEXT("visible"), Part->IsVisible());
        Object->SetBoolField(TEXT("collision_enabled"), Part->GetCollisionEnabled() != ECollisionEnabled::NoCollision);
        Object->SetBoolField(TEXT("simulating_physics"), Part->IsSimulatingPhysics());
#if WITH_EDITOR
        UMaterial* Material = Part->GetMaterial(0) ? Part->GetMaterial(0)->GetMaterial() : nullptr;
        if (!Material) return false;
        const auto* Color = Cast<UMaterialExpressionConstant3Vector>(Material->GetEditorOnlyData()->EmissiveColor.Expression);
        if (!Color) return false;
        Object->SetStringField(TEXT("material_name"),Material->GetName());
        Object->SetBoolField(TEXT("material_unlit"),Material->GetShadingModels().HasShadingModel(MSM_Unlit));
        Object->SetBoolField(TEXT("material_opaque"),Material->GetBlendMode() == BLEND_Opaque);
        Object->SetArrayField(TEXT("material_emissive_rgba"),{MakeShared<FJsonValueNumber>(Color->Constant.R),
            MakeShared<FJsonValueNumber>(Color->Constant.G),MakeShared<FJsonValueNumber>(Color->Constant.B),
            MakeShared<FJsonValueNumber>(Color->Constant.A)});
#endif
        Object->SetArrayField(TEXT("position_cm"), VectorJson(Part->GetComponentLocation()));
        Object->SetArrayField(TEXT("scale"), VectorJson(Part->GetComponentScale()));
        const FBox Bounds = Part->GetStaticMesh()->GetBoundingBox();
        Object->SetArrayField(TEXT("mesh_bounds_min"), VectorJson(Bounds.Min));
        Object->SetArrayField(TEXT("mesh_bounds_max"), VectorJson(Bounds.Max));
        const FQuat Q = Part->GetComponentQuat();
        Object->SetArrayField(TEXT("quaternion_xyzw"), {MakeShared<FJsonValueNumber>(Q.X), MakeShared<FJsonValueNumber>(Q.Y),
            MakeShared<FJsonValueNumber>(Q.Z), MakeShared<FJsonValueNumber>(Q.W)});
        Objects.Add(MakeShared<FJsonValueObject>(Object));
    }
    Json->SetArrayField(TEXT("objects"), Objects);
    FString Text;
    return FJsonSerializer::Serialize(Json, TJsonWriterFactory<>::Create(&Text)) &&
        FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}
