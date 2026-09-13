#include "WksimVehicleVisual.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"

const int32 FWksimVehicleVisual::HexSpins[6] = {1, -1, 1, -1, -1, 1};
namespace
{
constexpr double HexAngles[] = {90, 270, 330, 150, 30, 210};
UStaticMeshComponent* AddPart(AActor* ModelActor, const FString& Name, const TCHAR* Asset,
    const FVector& Location, const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator)
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

}

bool FWksimVehicleVisual::Build(const FString& Profile, AActor* Model,
    TArray<TObjectPtr<UStaticMeshComponent>>& Rotors)
{
    FString Json;
    TSharedPtr<FJsonObject> Root;
    const TSharedPtr<FJsonObject>* Assets = nullptr;
    double Version = 0;
    if (!Model || !Model->GetRootComponent() ||
        !FFileHelper::LoadFileToString(Json, *(FPaths::ProjectConfigDir() / TEXT("WksimVisualAssets.json"))) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root ||
        !Root->TryGetNumberField(TEXT("schema_version"), Version) || Version != 1 ||
        !Root->TryGetObjectField(TEXT("assets"), Assets) || (*Assets)->Values.Num() != 7)
    { UE_LOG(LogTemp, Error, TEXT("WKSIM invalid visual asset catalog")); return false; }
    const TCHAR* Keys[] = {TEXT("body_material"), TEXT("rotor_material"), TEXT("p450_body_mesh"),
        TEXT("rotor_cw_mesh"), TEXT("rotor_ccw_mesh"), TEXT("cylinder_mesh"), TEXT("cube_mesh")};
    for (const TCHAR* Key : Keys)
    {
        FString Value;
        if (!(*Assets)->TryGetStringField(Key, Value) ||
            !(Value.StartsWith(TEXT("/Game/")) || Value.StartsWith(TEXT("/Engine/")))) return false;
    }
    auto Asset = [Assets](const TCHAR* Key) { return (*Assets)->GetStringField(Key); };
    auto BodyMaterial = LoadObject<UMaterialInterface>(nullptr, *Asset(TEXT("body_material")));
    auto RotorMaterial = LoadObject<UMaterialInterface>(nullptr, *Asset(TEXT("rotor_material")));
    if (!BodyMaterial || !RotorMaterial) return false;
    Rotors.Reset();
    if (Profile == TEXT("hex"))
    {

        // Ground clearance is geometry-only; AuthoritativePose remains exactly source truth.
        const FVector Offset(0, 0, 10);
        auto Body = AddPart(Model, TEXT("HexBody"), *Asset(TEXT("cylinder_mesh")), Offset, FVector(.16, .16, .04));
        if (!Body) return false;
        Body->SetMaterial(0, BodyMaterial);
        for (int32 Index = 0; Index < 6; ++Index)
        {
            const double Angle = FMath::DegreesToRadians(HexAngles[Index]);
            const FVector Origin(22.5 * FMath::Cos(Angle), 22.5 * FMath::Sin(Angle), 0);
            auto Arm = AddPart(Model, FString::Printf(TEXT("HexArm_M%d"), Index + 1), *Asset(TEXT("cube_mesh")),
                Origin * .5 + Offset + FVector(0, 0, -2), FVector(.225, .018, .018), FRotator(0, HexAngles[Index], 0));
            if (!Arm) return false;
            Arm->SetMaterial(0, BodyMaterial);
            auto Rotor = AddPart(Model, FString::Printf(TEXT("HexRotor_M%d"), Index + 1),
                FWksimVehicleVisual::HexSpins[Index] > 0 ? *Asset(TEXT("rotor_cw_mesh")) : *Asset(TEXT("rotor_ccw_mesh")),
                Origin + Offset, FVector::OneVector);
            if (!Rotor) return false;
            const FVector Extent = Rotor->GetStaticMesh()->GetBounds().BoxExtent;
            const double Diameter = 2.0 * FMath::Max(Extent.X, Extent.Y);
            if (!FMath::IsFinite(Diameter) || Diameter <= 0)
            { FPlatformMisc::RequestExitWithStatus(true, 22); return false; }
            Rotor->SetRelativeScale3D(FVector(18.0 / Diameter));
            Rotor->SetMaterial(0, RotorMaterial);
            Rotors.Add(Rotor);
            UE_LOG(LogTemp, Display, TEXT("WKSIM_HEX motor=%d origin_cm=%s spin=%d mesh_extent_cm=%s uniform_scale=%.12f diameter_cm=18"),
                Index + 1, *Rotor->GetRelativeLocation().ToString(), FWksimVehicleVisual::HexSpins[Index], *Extent.ToString(), 18.0 / Diameter);
        }
        for (int32 Index = 0; Index < 4; ++Index)
        {
            auto Leg = AddPart(Model, FString::Printf(TEXT("HexLandingLeg_%d"), Index), *Asset(TEXT("cube_mesh")),
                FVector(Index < 2 ? -6 : 6, Index % 2 ? -6 : 6, -5) + Offset, FVector(.018, .018, .10));
            if (!Leg) return false;
            Leg->SetMaterial(0, BodyMaterial);
        }
        return true;
    }
    if (Profile == TEXT("p450"))
    {
        const FVector GeometryOffset(0, 0, 4.4560544192790985);
        UStaticMeshComponent* Body = AddPart(Model, TEXT("P450Body"), *Asset(TEXT("p450_body_mesh")), GeometryOffset, FVector::OneVector);
        if (!Body) return false;
        Body->SetMaterial(0, BodyMaterial);
        const FVector Motors[] = {FVector(14.65, 14.7, 15.1), FVector(-14.65, -14.7, 15.1),
                                 FVector(14.65, -14.7, 15.1), FVector(-14.65, 14.7, 15.1)};
        const TCHAR* MotorNames[] = {TEXT("FR"), TEXT("RL"), TEXT("FL"), TEXT("RR")};
        for (int32 Index = 0; Index < 4; ++Index)
        {
            UStaticMeshComponent* Rotor = AddPart(Model, FString::Printf(TEXT("P450Rotor_%s"), MotorNames[Index]),
                Index < 2 ? *Asset(TEXT("rotor_ccw_mesh")) : *Asset(TEXT("rotor_cw_mesh")),
                Motors[Index] + GeometryOffset, FVector::OneVector);
            if (!Rotor) return false;
            Rotor->SetMaterial(0, RotorMaterial);
            Rotors.Add(Rotor);
            UE_LOG(LogTemp, Display, TEXT("WKSIM_MODEL rotor=%s source_sdf_index=%d origin_cm=%s yaw_sign=%d"),
                MotorNames[Index], Index, *Rotor->GetRelativeLocation().ToString(), Index < 2 ? -1 : 1);
        }
        return true;
    }
    if (Profile == TEXT("ackermann"))
    {
        auto Body = AddPart(Model, TEXT("RoverBody"), *Asset(TEXT("cube_mesh")),
            FVector(0, 0, 40), FVector(1.4, .8, .3));
        if (!Body) return false;
        Body->SetMaterial(0, BodyMaterial);
        for (int32 Index = 0; Index < 4; ++Index)
        {
            auto Wheel = AddPart(Model, FString::Printf(TEXT("RoverWheel_%d"), Index),
                *Asset(TEXT("cylinder_mesh")), FVector(Index < 2 ? 50 : -50, Index % 2 ? 45 : -45, 15),
                FVector(.3, .3, .12), FRotator(0, 0, 90));
            if (!Wheel) return false;
            Wheel->SetMaterial(0, RotorMaterial);
        }
        UE_LOG(LogTemp, Display, TEXT("WKSIM_MODEL visual=ackermann wheelbase_cm=100 physics=external_flat_ground"));
        return true;
    }
    UE_LOG(LogTemp, Error, TEXT("WKSIM unsupported visual profile: %s"), *Profile);
    return false;
}
