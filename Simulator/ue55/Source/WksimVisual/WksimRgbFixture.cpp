#include "WksimRgbFixture.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionConstant3Vector.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#if PLATFORM_WINDOWS
#include "Windows/WindowsHWrapper.h"
#endif

namespace
{
int ModuleIdentityAnchor;
TArray<TSharedPtr<FJsonValue>> VectorJson(const FVector& V)
{
    return {MakeShared<FJsonValueNumber>(V.X), MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)};
}
}

bool AWksimRgbFixture::Configure(int32 Case, FString& Error)
{
    if (CaseId != -1 || Case < 0 || Case > 3) { Error = TEXT("Fixture case must be 0..3 and configured once"); return false; }
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
    if (CaseId < 0 || Parts.Num() != 3 || Materials.Num() != 3) return false;
    for (const UMaterial* Material : Materials) if (Material->IsCompiling()) return false;
    return true;
}

bool AWksimRgbFixture::WriteManifest(const FString& Path) const
{
    if (CaseId < 0) return false;
    auto Json = MakeShared<FJsonObject>();
    Json->SetStringField(TEXT("schema"), TEXT("wksim.rgb-calibration-visual.v1"));
    Json->SetNumberField(TEXT("case_id"), CaseId);
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
