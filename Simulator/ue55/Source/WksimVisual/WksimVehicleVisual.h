#pragma once
#include "CoreMinimal.h"

class AActor;
class UStaticMeshComponent;

// Owns visual assets and local geometry. No flight-stack or physics ownership.
struct FWksimVehicleVisual
{
    static const int32 HexSpins[6];
    static bool Build(const FString& Profile, AActor* Actor,
                      TArray<TObjectPtr<UStaticMeshComponent>>& Rotors);
};
