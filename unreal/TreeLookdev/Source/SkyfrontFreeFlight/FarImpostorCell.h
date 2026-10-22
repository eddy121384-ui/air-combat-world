#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FarImpostorCell.generated.h"

// Far-LOD research (docs/skyfront-far-lod-research-v1.md section 10): holder of one forest tile's tree impostors for one far-thinning
// hash band (instanced static mesh components added by adapters/unreal/ntwforest/fi_build.py). World Partition places an actor by its
// streaming bounds; the cards' render bounds stick out of the 1 km tile (crowns + WPO room), which would push every tile one grid level up
// (2 km cells, unaligned) and load it far too early. The streaming bounds are therefore the tile footprint itself, so each tile streams as
// exactly one 1 km cell of its band's 2D grid. Rendering / culling still use the real component bounds.
UCLASS()
class SKYFRONTFREEFLIGHT_API AFarImpostorCell : public AActor
{
	GENERATED_BODY()

public:
	AFarImpostorCell();

	// Tile footprint (XY), used as the World Partition runtime streaming bounds when valid.
	UPROPERTY(EditAnywhere, Category = "FarLod")
	FBox StreamingFootprint = FBox(ForceInit);

#if WITH_EDITOR
	virtual void GetStreamingBounds(FBox& OutRuntimeBounds, FBox& OutEditorBounds) const override;
#endif
};
