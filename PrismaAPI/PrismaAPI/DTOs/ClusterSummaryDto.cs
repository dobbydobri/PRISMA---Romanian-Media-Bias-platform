namespace PrismaAPI.DTOs;

public class ClusterSummaryDto
{
    public string? ClusterTitle { get; set; }

    public string? NeutralSummary { get; set; }

    public List<string> KeyPoints { get; set; } = new();
}
