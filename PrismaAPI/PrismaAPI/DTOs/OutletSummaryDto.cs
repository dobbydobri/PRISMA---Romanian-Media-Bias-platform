namespace PrismaAPI.DTOs;

public class OutletSummaryDto
{
    public int Id { get; set; }

    public string Name { get; set; } = string.Empty;

    public string OutletType { get; set; } = string.Empty;

    public string? Url { get; set; }

    public int TotalArticles { get; set; }

    public double? AvgCoalition { get; set; }

    public double? AvgEuAxis { get; set; }

    public double? AvgSensationalism { get; set; }

    public double? AvgCitationQuality { get; set; }

    public double? AvgRhetoricIntensity { get; set; }

    public string? DominantTopic { get; set; }

    public string? DominantFraming { get; set; }
}
