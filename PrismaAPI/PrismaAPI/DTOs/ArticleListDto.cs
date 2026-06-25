namespace PrismaAPI.DTOs;

public class ArticleListDto
{
    public long Id { get; set; }

    public string Title { get; set; } = string.Empty;

    public string? Url { get; set; }

    public string OutletName { get; set; } = string.Empty;

    public DateTime? PublishedAt { get; set; }

    public int? ClusterId { get; set; }

    public string? ClusterLabel { get; set; }

    public double? ScoreSensationalism { get; set; }

    public double? ScoreCitationQuality { get; set; }

    public double? ScoreRhetoricIntensity { get; set; }

    public string? TfGovStance { get; set; }

    public string? TfSovereignism { get; set; }

    public string? TfFraming { get; set; }

    public string? TfTopic { get; set; }
}
