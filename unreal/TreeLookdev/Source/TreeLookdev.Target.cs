using UnrealBuildTool;

public class TreeLookdevTarget : TargetRules
{
	public TreeLookdevTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyfrontFreeFlight");
	}
}
