using UnrealBuildTool;

// Skyfront Homeland free-flight prototype v1: one paper plane, chase camera, touch stick + throttle, canvas HUD.
// Runtime only; no content assets (the plane is a ProceduralMeshComponent, the HUD is drawn on the canvas).
public class SkyfrontFreeFlight : ModuleRules
{
	public SkyfrontFreeFlight(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "ProceduralMeshComponent", "LevelSequence", "MovieScene", "RHI" });
	}
}
