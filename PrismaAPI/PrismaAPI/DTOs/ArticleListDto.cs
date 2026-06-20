namespace PrismaAPI.DTOs;

public class ArticleListDto
{
    public long Id { get; set; }

    public string Title { get; set; } = string.Empty;

    public string OutletName { get; set; } = string.Empty;

    public DateTime? PublishedAt { get; set; }

    public int? ClusterId { get; set; }

    public string? ClusterLabel { get; set; }

    public double? ScoreSensationalism { get; set; }

    public double? ScoreCitationQuality { get; set; }

    public double? ScoreRhetoricIntensity { get; set; }

    public double? PredCoalition { get; set; }

    public double? PredEuAxis { get; set; }

    public int? PredIsPolitical { get; set; }

    public string? LlmFraming { get; set; }

    public string? LlmTopic { get; set; }
}
