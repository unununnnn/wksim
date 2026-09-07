#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "WksimRgbSensor.generated.h"

class UTextureRenderTarget2D;
struct FWksimRgbWork;

// Expose the engine's protected admission gate without duplicating its cvar logic.
UCLASS()
class UWksimRgbCapture : public USceneCaptureComponent2D
{
    GENERATED_BODY()
public:
    bool IsDetailCulled() const { return IsCulledByDetailMode(); }
};

// UE boundary: centimeters, +X forward / +Y right / +Z up. No implicit NED conversion.
struct FWksimRgbConfig
{
    FString RunId, InstanceId, Epoch, VehicleId, SensorId, OutputDirectory;
    int32 Width = 640, Height = 480;
    float HorizontalFovDegrees = 90.f;
    FTransform CameraInVehicle = FTransform::Identity;
};

struct FWksimRgbRequest
{
    FString RunId, InstanceId, Epoch;
    int64 Step = -1;
    double SimTimeSeconds = -1;
    // Caller must have applied this authoritative state to all relevant scene actors.
    FTransform CameraWorldPose = FTransform::Identity;
};

UCLASS()
class WKSIMVISUAL_API UWksimRgbSensor : public UActorComponent
{
    GENERATED_BODY()
public:
    UWksimRgbSensor();
    bool Configure(const FWksimRgbConfig& InConfig, FString& Error);
    bool RequestCapture(const FWksimRgbRequest& Request, FString& Error);
    // Call every game tick. Returns only a completed current-generation metadata path.
    bool Poll(FString& MetadataPath, FString& Error);
    // Invalidates publication immediately, but drains existing GPU/IO work before reuse.
    void Invalidate();
    bool IsBusy() const { return Work.IsValid(); }
    uint64 DroppedBusy = 0, DroppedStale = 0, Failed = 0;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    UPROPERTY(Transient) TObjectPtr<UWksimRgbCapture> Capture;
    UPROPERTY(Transient) TObjectPtr<UTextureRenderTarget2D> Target;
    FWksimRgbConfig Config;
    TSharedPtr<FWksimRgbWork, ESPMode::ThreadSafe> Work;
    uint64 Frame = 0;
    int64 LastStep = -1;
    double LastSimTime = -1;
    bool bConfigured = false;
};
