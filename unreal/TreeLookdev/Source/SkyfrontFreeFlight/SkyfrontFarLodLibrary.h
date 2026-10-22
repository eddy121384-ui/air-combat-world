#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkyfrontFarLodLibrary.generated.h"

// Far-LOD research (docs/skyfront-far-lod-research-v1.md, v2 section): World Partition setup for the streamed tree-impostor layer.
// Editor-only bodies (the cooked game gets no-ops); called from adapters/unreal/ntwforest/fi_build.py.
UCLASS()
class SKYFRONTFREEFLIGHT_API USkyfrontFarLodLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// Adds (or updates) a named runtime partition of the map's RuntimeHashSet, cloned from partition 0 (the forest's LHGrid) with its
	// own cell size / loading range / priority and no HLOD setups. Actors are mapped to it through AActor::RuntimeGrid. Returns JSON.
	UFUNCTION(BlueprintCallable, Category = "Skyfront|FarLod", meta = (WorldContext = "WorldContextObject"))
	static FString EnsureRuntimePartition(UObject* WorldContextObject, FName Name, int32 CellSizeCm, int32 LoadingRangeCm, int32 Priority);

	// Sets a partition's 2D flag (loading by XY distance, cells unbounded in Z) and grid origin (cm). Returns JSON.
	UFUNCTION(BlueprintCallable, Category = "Skyfront|FarLod", meta = (WorldContext = "WorldContextObject"))
	static FString SetRuntimePartitionShape(UObject* WorldContextObject, FName Name, bool bIs2D, float OriginX, float OriginY);

	// Removes a named runtime partition (never partition 0). Returns JSON.
	UFUNCTION(BlueprintCallable, Category = "Skyfront|FarLod", meta = (WorldContext = "WorldContextObject"))
	static FString RemoveRuntimePartition(UObject* WorldContextObject, FName Name);

	// Lists the runtime partitions (name, class, cell size, loading range). Returns JSON.
	UFUNCTION(BlueprintCallable, Category = "Skyfront|FarLod", meta = (WorldContext = "WorldContextObject"))
	static FString DescribeRuntimePartitions(UObject* WorldContextObject);
};
