#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "RenderCommandFence.h"
#include "WksimVisualGameMode.generated.h"

class FSocket;
class ACameraActor;
class UStaticMeshComponent;

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
private:
    bool ApplyPacket(const uint8* Bytes, int32 Count, FString& Ack);
    UStaticMeshComponent* AddPart(const FString& Name, const TCHAR* Asset, const FVector& Location,
                                const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator);
    UPROPERTY() TObjectPtr<AActor> Vehicle;
    UPROPERTY() TObjectPtr<ACameraActor> Camera;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Rotors;
    TArray<double> RotorRpm;
    FSocket* Socket = nullptr;
    FString CaptureDirectory;
    double NextCaptureWall = 0.0;
    int64 CaptureIndex = 0;
    int32 LaunchPort = 19060;
    int32 ReadyFrames = 0;
    bool bRenderReady = false;
    bool bStartupFenceQueued = false;
    FRenderCommandFence StartupFence;
};

UCLASS()
class AWksimHud : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};
