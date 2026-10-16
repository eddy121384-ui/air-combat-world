#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "XinyiWorldPartitionAuditLibrary.generated.h"

/** Read-only UE5.8 World Partition state not exposed to editor Python. */
UCLASS()
class XINYILANDSCAPEBRIDGE_API UXinyiWorldPartitionAuditLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintPure, Category = "XinyiV2|WorldPartition")
    static FString InspectCurrentEditorWorldPartition();
};
