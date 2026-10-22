#include "FarImpostorCell.h"

#include "Components/SceneComponent.h"

AFarImpostorCell::AFarImpostorCell()
{
	PrimaryActorTick.bCanEverTick = false;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	RootComponent = Root;
}

#if WITH_EDITOR
void AFarImpostorCell::GetStreamingBounds(FBox& OutRuntimeBounds, FBox& OutEditorBounds) const
{
	Super::GetStreamingBounds(OutRuntimeBounds, OutEditorBounds);
	if (StreamingFootprint.IsValid)
	{
		OutRuntimeBounds = StreamingFootprint;
	}
}
#endif
