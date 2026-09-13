#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "WksimDepthSensor.generated.h"

class UTextureRenderTarget2D;
struct FWksimDepthWork;

// Expose the engine's protected admission gate without duplicating its cvar logic.
UCLASS()
class UWksimDepthCapture : public USceneCaptureComponent2D
{
    GENERATED_BODY()
public:
    bool IsDetailCulled() const { return IsCulledByDetailMode(); }
};

// UE boundary: centimeters, +X forward / +Y right / +Z up. No implicit NED conversion.
struct FWksimDepthConfig
{
    FString RunId, InstanceId, Epoch, StreamId, VehicleId, SensorId, OutputDirectory;
    int32 Width = 160, Height = 120;
    int64 Generation = 0;
    float MaxDepthMeters = 100.f;
    float HorizontalFovDegrees = 90.f;
    FTransform CameraInVehicle = FTransform::Identity;
};

struct FWksimDepthRequest
{
    FString RunId, InstanceId, Epoch, StreamId;
    int64 Step = -1;
    double SimTimeSeconds = -1;
    // Caller must have applied this authoritative state to all relevant scene actors.
    FTransform CameraWorldPose = FTransform::Identity;
};

UCLASS()
class WKSIMVISUAL_API UWksimDepthSensor : public UActorComponent
{
    GENERATED_BODY()
public:
    UWksimDepthSensor();
    bool Configure(const FWksimDepthConfig& InConfig, FString& Error);
    bool RequestCapture(const FWksimDepthRequest& Request, FString& Error);
    // Call every game tick. Returns only a completed current-generation metadata path.
    bool Poll(FString& MetadataPath, FString& Error);
    // Invalidates publication immediately, but drains existing GPU/IO work before reuse.
    void Invalidate();
    bool IsBusy() const { return Work.IsValid(); }
    uint64 DroppedBusy = 0, DroppedStale = 0, Failed = 0;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    UPROPERTY(Transient) TObjectPtr<UWksimDepthCapture> Capture;
    UPROPERTY(Transient) TObjectPtr<UTextureRenderTarget2D> Target;
    FWksimDepthConfig Config;
    TSharedPtr<FWksimDepthWork, ESPMode::ThreadSafe> Work;
    uint64 Frame = 0;
    int64 LastStep = -1;
    double LastSimTime = -1;
    bool bConfigured = false;
};
