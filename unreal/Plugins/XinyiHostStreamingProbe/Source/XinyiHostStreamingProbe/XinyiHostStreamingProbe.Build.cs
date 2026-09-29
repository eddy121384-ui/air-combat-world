using UnrealBuildTool;

public class XinyiHostStreamingProbe : ModuleRules
{
    public XinyiHostStreamingProbe(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "Json", "Landscape", "PhysicsCore"
        });
    }
}
