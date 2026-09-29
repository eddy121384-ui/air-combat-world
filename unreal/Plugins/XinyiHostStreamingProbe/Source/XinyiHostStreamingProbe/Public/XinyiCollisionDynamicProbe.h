#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "XinyiCollisionDynamicProbe.generated.h"

class UBoxComponent;

UCLASS()
class XINYIHOSTSTREAMINGPROBE_API AXinyiCollisionDynamicProbe final : public AActor
{
    GENERATED_BODY()

public:
    AXinyiCollisionDynamicProbe();

    UPROPERTY(VisibleAnywhere)
    TObjectPtr<UBoxComponent> CollisionBox;

    UPROPERTY(Transient)
    TObjectPtr<AActor> ObservedHitActor;

    UPROPERTY(Transient)
    TObjectPtr<UPrimitiveComponent> ObservedHitComponent;

    bool bObservedBlockingHit = false;
    FVector ObservedHitLocation = FVector::ZeroVector;

private:
    UFUNCTION()
    void HandleComponentHit(UPrimitiveComponent* HitComponent, AActor* OtherActor,
        UPrimitiveComponent* OtherComponent, FVector NormalImpulse, const FHitResult& Hit);
};
