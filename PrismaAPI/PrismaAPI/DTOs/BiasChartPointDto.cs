namespace PrismaAPI.DTOs;

public class BiasChartPointDto
{
    public string OutletName { get; set; } = string.Empty;

    public string OutletType { get; set; } = string.Empty;

    public double AvgCoalition { get; set; }

    public double AvgEuAxis { get; set; }

    public int ArticleCount { get; set; }
}
