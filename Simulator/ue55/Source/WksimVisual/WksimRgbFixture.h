#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WksimRgbFixture.generated.h"

class UStaticMeshComponent;
class UMaterial;

// Opt-in visual calibration target. Never supplies terrain or collision physics.
UCLASS()
class WKSIMVISUAL_API AWksimRgbFixture : public AActor
{
    GENERATED_BODY()
public:
    bool Configure(int32 Case, FString& Error);
    bool IsReady() const;
    bool WriteManifest(const FString& Path) const;
private:
    int32 CaseId = -1;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Parts;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterial>> Materials;
};
