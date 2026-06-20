namespace PrismaAPI.DTOs;

public class CoverageGapDto
{
    public int ClusterId { get; set; }

    public string? ClusterLabel { get; set; }

    public int TotalOutlets { get; set; }

    public int CoveringOutlets { get; set; }

    public List<string> MissingOutlets { get; set; } = new();

    public List<string> PresentOutlets { get; set; } = new();
}
