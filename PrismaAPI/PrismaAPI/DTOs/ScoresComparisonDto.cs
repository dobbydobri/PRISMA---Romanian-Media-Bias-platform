namespace PrismaAPI.DTOs;

public class ScoresComparisonDto
{
    public string OutletName { get; set; } = string.Empty;

    public string OutletType { get; set; } = string.Empty;

    public double? AvgSensationalism { get; set; }

    public double? AvgCitationQuality { get; set; }

    public double? AvgRhetoricIntensity { get; set; }
}
