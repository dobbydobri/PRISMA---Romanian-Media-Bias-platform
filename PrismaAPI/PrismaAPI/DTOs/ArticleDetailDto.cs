namespace PrismaAPI.DTOs;

public class ArticleDetailDto
{
    public long Id { get; set; }

    public string Title { get; set; } = string.Empty;

    public string? ContentText { get; set; }

    public string? Url { get; set; }

    public string OutletName { get; set; } = string.Empty;

    public int OutletId { get; set; }

    public DateTime? PublishedAt { get; set; }

    public string[]? Authors { get; set; }


    public double? ScoreSensationalism { get; set; }

    public double? ScoreCitationQuality { get; set; }

    public double? ScoreRhetoricIntensity { get; set; }

    public string? TfGovStance { get; set; }

    public string? TfSovereignism { get; set; }

    public string? TfFraming { get; set; }

    public string? TfTopic { get; set; }


    public int? ClusterId { get; set; }

    public int? SubClusterId { get; set; }

    public string? ClusterLabel { get; set; }

    public string[]? ClusterTerms { get; set; }

    public string[]? ClusterEntities { get; set; }


    public List<ArticleEntityDto> Entities { get; set; } = new();

    public List<FactCheckDto>? RelatedFactChecks { get; set; }
}

public class ArticleEntityDto
{
    public string EntityText { get; set; } = string.Empty;

    public string EntityLabel { get; set; } = string.Empty;
}
