#include "XinyiCollisionDynamicProbe.h"

#include "Components/BoxComponent.h"

AXinyiCollisionDynamicProbe::AXinyiCollisionDynamicProbe()
{
    PrimaryActorTick.bCanEverTick = false;
    CollisionBox = CreateDefaultSubobject<UBoxComponent>(TEXT("CollisionBox"));
    SetRootComponent(CollisionBox);
    CollisionBox->SetBoxExtent(FVector(40.0, 40.0, 40.0));
    CollisionBox->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    CollisionBox->SetCollisionObjectType(ECC_PhysicsBody);
    CollisionBox->SetCollisionResponseToAllChannels(ECR_Block);
    CollisionBox->SetNotifyRigidBodyCollision(true);
    CollisionBox->SetEnableGravity(false);
    CollisionBox->BodyInstance.bUseCCD = true;
    CollisionBox->OnComponentHit.AddDynamic(this, &AXinyiCollisionDynamicProbe::HandleComponentHit);
}

void AXinyiCollisionDynamicProbe::HandleComponentHit(UPrimitiveComponent*, AActor* OtherActor,
    UPrimitiveComponent* OtherComponent, FVector, const FHitResult& Hit)
{
    bObservedBlockingHit = Hit.bBlockingHit;
    ObservedHitActor = OtherActor;
    ObservedHitComponent = OtherComponent;
    ObservedHitLocation = Hit.Location;
}
