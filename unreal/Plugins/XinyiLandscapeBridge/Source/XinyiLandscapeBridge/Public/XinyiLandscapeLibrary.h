#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "XinyiLandscapeLibrary.generated.h"

/**
 * Deliberately tiny UE5.8 editor bridge.
 *
 * It does not fetch, resample, align, repair, or reinterpret terrain data.
 * Python owns the validated source/elevation contract. This bridge only turns
 * an already-encoded little-endian RAW16 buffer into a real ALandscape because
 * UE5.8 does not expose the from-zero ALandscape::Import path to Python.
 */
UCLASS()
class XINYILANDSCAPEBRIDGE_API UXinyiLandscapeLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "XinyiV2|Landscape")
    static FString CreateLandscapeFromRaw16(
        const FString& Raw16Path,
        int32 SizeX,
        int32 SizeY,
        int32 NumSubsections,
        int32 SubsectionSizeQuads,
        FVector LocationCm,
        FVector ScaleXYZ,
        const FString& ActorLabel);

    UFUNCTION(BlueprintPure, Category = "XinyiV2|Landscape")
    static FString InspectLandscapeByLabel(const FString& ActorLabel);
};
