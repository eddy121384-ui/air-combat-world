using UnrealBuildTool;

public class TreeLookdevEditorTarget : TargetRules
{
	public TreeLookdevEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyfrontFreeFlight");
	}
}
