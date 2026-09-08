#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "RenderCommandFence.h"
#include "WksimRgbSensor.h"
#include "WksimDepthSensor.h"
#include "WksimVisualGameMode.generated.h"

class FSocket;
class ACameraActor;
class UStaticMeshComponent;
class AWksimRgbFixture;

USTRUCT()
struct FWksimJointVehicle
{
    GENERATED_BODY()
    UPROPERTY() TObjectPtr<AActor> Actor;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Rotors;
    FVector PositionNed = FVector::ZeroVector;
    int64 Step = -1;
    double ReceivedWall = 0.0;
    double SourceWall = 0.0;
    FString Phase;
};

UCLASS()
class AWksimVisualGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AWksimVisualGameMode();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    FString RunId;
    FString VehicleId;
    FVector PositionNed = FVector::ZeroVector;
    double SourceTime = 0.0;
    double DisplayWallTime = 0.0;
    double LastReceivedWall = 0.0;
    int64 LastSequence = -1;
    int64 Rejected = 0;
    bool IsStale() const;
    bool IsRenderReady() const { return bRenderReady; }
    bool IsJointStale(int32 Index) const;
    UPROPERTY() TArray<FWksimJointVehicle> JointVehicles;
    int32 SelectedVehicleId = 1;
    int64 JointGeneration = 0;
private:
    bool ApplyPacket(const uint8* Bytes, int32 Count, FString& Ack);
    bool ApplyJointPacket(const TSharedPtr<class FJsonObject>& Object, FString& Ack);
    bool LoadRgbConfig(const FString& Path);
    void TickRgb();
    bool LoadDepthConfig(const FString& Path);
    void TickDepth();
    UStaticMeshComponent* AddPart(AActor* ModelActor, const FString& Name, const TCHAR* Asset, const FVector& Location,
                                const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator);
    UPROPERTY() TObjectPtr<AActor> Vehicle;
    UPROPERTY() TObjectPtr<ACameraActor> Camera;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Rotors;
    TArray<double> RotorRpm;
    FString InstanceId;
    FString JointEpoch;
    int64 JointStep = -1;
    int64 LastViewRequest = -1;
    FSocket* Socket = nullptr;
    FString CaptureDirectory;
    double NextCaptureWall = 0.0;
    int64 CaptureIndex = 0;
    int32 LaunchPort = 19060;
    int32 ReadyFrames = 0;
    bool bRenderReady = false;
    bool bStartupFenceQueued = false;
    FRenderCommandFence StartupFence;
    UPROPERTY(Transient) TObjectPtr<UWksimRgbSensor> RgbSensor;
    FWksimRgbConfig RgbConfig;
    FString RgbEpoch;
    int64 RgbLastStep = -1;
    int64 RgbIntervalSteps = 100;
    int32 RgbNotifyPort = 0;
    bool bRgbEnabled = true;
    int64 LastRgbRequest = -1;
    UPROPERTY(Transient) TObjectPtr<AWksimRgbFixture> RgbFixture;
    UPROPERTY(Transient) TObjectPtr<UWksimDepthSensor> DepthSensor;
    FWksimDepthConfig DepthConfig;
    FString DepthEpoch;
    int64 DepthLastStep = -1, DepthIntervalSteps = 100;
    int32 DepthNotifyPort = 0;
};

UCLASS()
class AWksimHud : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};
