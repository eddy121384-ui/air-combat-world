#include "SkyfrontFarLodLibrary.h"

#include "Engine/World.h"
#include "UObject/UnrealType.h"
#include "WorldPartition/WorldPartition.h"

namespace
{
#if WITH_EDITOR
	UObject* RuntimeHashOf(UObject* WorldContextObject)
	{
		UWorld* W = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
		UWorldPartition* WP = W ? W->GetWorldPartition() : nullptr;
		FObjectProperty* P = WP ? FindFProperty<FObjectProperty>(UWorldPartition::StaticClass(), TEXT("RuntimeHash")) : nullptr;
		return P ? P->GetObjectPropertyValue_InContainer(WP) : nullptr;
	}

	template <typename TProp, typename TValue>
	bool SetProp(UObject* Obj, const TCHAR* Name, TValue Value)
	{
		TProp* P = Obj ? FindFProperty<TProp>(Obj->GetClass(), Name) : nullptr;
		if (!P)
		{
			return false;
		}
		P->SetPropertyValue_InContainer(Obj, Value);
		return true;
	}

	FString Describe(UObject* Hash)
	{
		FArrayProperty* Arr = FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("RuntimePartitions"));
		FStructProperty* Inner = Arr ? CastField<FStructProperty>(Arr->Inner) : nullptr;
		if (!Inner)
		{
			return TEXT("{\"error\":\"no RuntimePartitions\"}");
		}
		FObjectProperty* MainProp = FindFProperty<FObjectProperty>(Inner->Struct, TEXT("MainLayer"));
		FNameProperty* NameProp = FindFProperty<FNameProperty>(Inner->Struct, TEXT("Name"));
		FScriptArrayHelper H(Arr, Arr->ContainerPtrToValuePtr<void>(Hash));
		FString Out = FString::Printf(TEXT("{\"hash_class\":\"%s\",\"partitions\":["), *Hash->GetClass()->GetName());
		for (int32 i = 0; i < H.Num(); ++i)
		{
			uint8* E = H.GetRawPtr(i);
			UObject* Main = MainProp->GetObjectPropertyValue(MainProp->ContainerPtrToValuePtr<void>(E));
			const FIntProperty* R = Main ? FindFProperty<FIntProperty>(Main->GetClass(), TEXT("LoadingRange")) : nullptr;
			const FUInt32Property* C = Main ? FindFProperty<FUInt32Property>(Main->GetClass(), TEXT("CellSize")) : nullptr;
			const FIntProperty* Pr = Main ? FindFProperty<FIntProperty>(Main->GetClass(), TEXT("Priority")) : nullptr;
			const FBoolProperty* B2 = Main ? FindFProperty<FBoolProperty>(Main->GetClass(), TEXT("bIs2D")) : nullptr;
			const FStructProperty* Or = Main ? FindFProperty<FStructProperty>(Main->GetClass(), TEXT("Origin")) : nullptr;
			const FVector Org = Or ? *Or->ContainerPtrToValuePtr<FVector>(Main) : FVector::ZeroVector;
			Out += FString::Printf(TEXT("%s{\"name\":\"%s\",\"class\":\"%s\",\"cell_size_cm\":%u,\"loading_range_cm\":%d,\"priority\":%d,\"is_2d\":%s,\"origin\":[%.0f,%.0f]}"), i ? TEXT(",") : TEXT(""),
				*NameProp->GetPropertyValue(NameProp->ContainerPtrToValuePtr<void>(E)).ToString(), Main ? *Main->GetClass()->GetName() : TEXT("null"),
				C ? C->GetPropertyValue_InContainer(Main) : 0u, R ? R->GetPropertyValue_InContainer(Main) : -1, Pr ? Pr->GetPropertyValue_InContainer(Main) : 0,
				B2 && B2->GetPropertyValue_InContainer(Main) ? TEXT("true") : TEXT("false"), Org.X, Org.Y);
		}
		return Out + TEXT("]}");
	}
#endif
}

FString USkyfrontFarLodLibrary::EnsureRuntimePartition(UObject* WorldContextObject, FName Name, int32 CellSizeCm, int32 LoadingRangeCm, int32 Priority)
{
#if WITH_EDITOR
	UObject* Hash = RuntimeHashOf(WorldContextObject);
	FArrayProperty* Arr = Hash ? FindFProperty<FArrayProperty>(Hash->GetClass(), TEXT("RuntimePartitions")) : nullptr;
	FStructProperty* Inner = Arr ? CastField<FStructProperty>(Arr->Inner) : nullptr;
	if (!Inner)
	{
		return TEXT("{\"error\":\"no RuntimeHashSet partitions\"}");
	}
	FObjectProperty* MainProp = FindFProperty<FObjectProperty>(Inner->Struct, TEXT("MainLayer"));
	FNameProperty* NameProp = FindFProperty<FNameProperty>(Inner->Struct, TEXT("Name"));
	FArrayProperty* HlodProp = FindFProperty<FArrayProperty>(Inner->Struct, TEXT("HLODSetups"));
	FScriptArrayHelper H(Arr, Arr->ContainerPtrToValuePtr<void>(Hash));
	if (H.Num() == 0)
	{
		return TEXT("{\"error\":\"no partition 0 to clone\"}");
	}
	Hash->Modify();
	int32 Index = INDEX_NONE;
	for (int32 i = 0; i < H.Num(); ++i)
	{
		if (NameProp->GetPropertyValue(NameProp->ContainerPtrToValuePtr<void>(H.GetRawPtr(i))) == Name)
		{
			Index = i;
		}
	}
	if (Index == INDEX_NONE)
	{
		Index = H.AddValue();
		uint8* Src = H.GetRawPtr(0);
		uint8* Dst = H.GetRawPtr(Index);
		NameProp->SetPropertyValue(NameProp->ContainerPtrToValuePtr<void>(Dst), Name);
		UObject* SrcMain = MainProp->GetObjectPropertyValue(MainProp->ContainerPtrToValuePtr<void>(Src));
		UObject* NewMain = DuplicateObject<UObject>(SrcMain, Hash);
		MainProp->SetObjectPropertyValue(MainProp->ContainerPtrToValuePtr<void>(Dst), NewMain);
		if (HlodProp)
		{
			FScriptArrayHelper Hl(HlodProp, HlodProp->ContainerPtrToValuePtr<void>(Dst));
			Hl.EmptyValues();
		}
	}
	UObject* Main = MainProp->GetObjectPropertyValue(MainProp->ContainerPtrToValuePtr<void>(H.GetRawPtr(Index)));
	if (!Main)
	{
		return TEXT("{\"error\":\"partition has no main layer\"}");
	}
	Main->Modify();
	const bool bOk = SetProp<FUInt32Property>(Main, TEXT("CellSize"), (uint32)CellSizeCm) && SetProp<FIntProperty>(Main, TEXT("LoadingRange"), LoadingRangeCm)
		&& SetProp<FIntProperty>(Main, TEXT("Priority"), Priority);
	SetProp<FNameProperty>(Main, TEXT("Name"), Name);   // the partition object's own name, when the class has one
	Hash->MarkPackageDirty();
	return FString::Printf(TEXT("{\"index\":%d,\"set_ok\":%s,\"now\":%s}"), Index, bOk ? TEXT("true") : TEXT("false"), *Describe(Hash));
#else
	return TEXT("{\"error\":\"editor only\"}");
#endif
}

#if WITH_EDITOR
namespace
{
	// Index of the named partition (or INDEX_NONE) and the pieces needed to edit it.
	struct FPartitionAccess
	{
		UObject* Hash = nullptr;
		FArrayProperty* Arr = nullptr;
		FObjectProperty* MainProp = nullptr;
		FNameProperty* NameProp = nullptr;
		int32 Index = INDEX_NONE;
	};
	FPartitionAccess FindPartition(UObject* WorldContextObject, FName Name)
	{
		FPartitionAccess A;
		A.Hash = RuntimeHashOf(WorldContextObject);
		A.Arr = A.Hash ? FindFProperty<FArrayProperty>(A.Hash->GetClass(), TEXT("RuntimePartitions")) : nullptr;
		FStructProperty* Inner = A.Arr ? CastField<FStructProperty>(A.Arr->Inner) : nullptr;
		if (!Inner)
		{
			return A;
		}
		A.MainProp = FindFProperty<FObjectProperty>(Inner->Struct, TEXT("MainLayer"));
		A.NameProp = FindFProperty<FNameProperty>(Inner->Struct, TEXT("Name"));
		FScriptArrayHelper H(A.Arr, A.Arr->ContainerPtrToValuePtr<void>(A.Hash));
		for (int32 i = 0; i < H.Num(); ++i)
		{
			if (A.NameProp->GetPropertyValue(A.NameProp->ContainerPtrToValuePtr<void>(H.GetRawPtr(i))) == Name)
			{
				A.Index = i;
			}
		}
		return A;
	}
}
#endif

FString USkyfrontFarLodLibrary::SetRuntimePartitionShape(UObject* WorldContextObject, FName Name, bool bIs2D, float OriginX, float OriginY)
{
#if WITH_EDITOR
	FPartitionAccess A = FindPartition(WorldContextObject, Name);
	if (A.Index == INDEX_NONE)
	{
		return TEXT("{\"error\":\"no such partition\"}");
	}
	FScriptArrayHelper H(A.Arr, A.Arr->ContainerPtrToValuePtr<void>(A.Hash));
	UObject* Main = A.MainProp->GetObjectPropertyValue(A.MainProp->ContainerPtrToValuePtr<void>(H.GetRawPtr(A.Index)));
	if (!Main)
	{
		return TEXT("{\"error\":\"no main layer\"}");
	}
	Main->Modify();
	bool bOk = false;
	if (FBoolProperty* B = FindFProperty<FBoolProperty>(Main->GetClass(), TEXT("bIs2D")))
	{
		B->SetPropertyValue_InContainer(Main, bIs2D);
		bOk = true;
	}
	if (FStructProperty* O = FindFProperty<FStructProperty>(Main->GetClass(), TEXT("Origin")))
	{
		*O->ContainerPtrToValuePtr<FVector>(Main) = FVector(OriginX, OriginY, 0.0);
	}
	else
	{
		bOk = false;
	}
	A.Hash->MarkPackageDirty();
	return FString::Printf(TEXT("{\"set_ok\":%s,\"now\":%s}"), bOk ? TEXT("true") : TEXT("false"), *Describe(A.Hash));
#else
	return TEXT("{\"error\":\"editor only\"}");
#endif
}

FString USkyfrontFarLodLibrary::RemoveRuntimePartition(UObject* WorldContextObject, FName Name)
{
#if WITH_EDITOR
	FPartitionAccess A = FindPartition(WorldContextObject, Name);
	if (A.Index <= 0)
	{
		return TEXT("{\"removed\":false}");
	}
	A.Hash->Modify();
	FScriptArrayHelper H(A.Arr, A.Arr->ContainerPtrToValuePtr<void>(A.Hash));
	H.RemoveValues(A.Index, 1);
	A.Hash->MarkPackageDirty();
	return FString::Printf(TEXT("{\"removed\":true,\"now\":%s}"), *Describe(A.Hash));
#else
	return TEXT("{\"error\":\"editor only\"}");
#endif
}

FString USkyfrontFarLodLibrary::DescribeRuntimePartitions(UObject* WorldContextObject)
{
#if WITH_EDITOR
	UObject* Hash = RuntimeHashOf(WorldContextObject);
	return Hash ? Describe(Hash) : TEXT("{\"error\":\"no runtime hash\"}");
#else
	return TEXT("{\"error\":\"editor only\"}");
#endif
}
