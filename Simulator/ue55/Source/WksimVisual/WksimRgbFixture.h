#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WksimRgbFixture.generated.h"

class UStaticMeshComponent;
class UMaterial;
struct FWksimRgbRequest;

// Opt-in visual calibration target. Never supplies terrain or collision physics.
UCLASS()
class WKSIMVISUAL_API AWksimRgbFixture : public AActor
{
    GENERATED_BODY()
public:
    bool Configure(int32 Case, FString& Error);
    bool IsReady() const;
    bool WriteManifest(const FString& Path) const;
    bool IsArUco() const { return CaseId == 4; }
    bool AdvanceArUco(const FWksimRgbRequest& Request, int64 Generation, const FString& Directory);
private:
    bool ConfigureArUco(FString& Error);
    FString SceneEpoch;
    int64 SceneFirstStep = -1, SceneStep = -1, SceneGeneration = -1;
    FString SceneRun, SceneInstance, SceneStream;
    FTransform SceneCamera;
    int32 CaseId = -1;
    UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Parts;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterial>> Materials;
};
