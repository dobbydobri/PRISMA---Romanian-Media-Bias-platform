namespace PrismaAPI.DTOs.Search;

public class SearchResponse
{
    public string Query { get; set; } = null!;

    public int ResultCount { get; set; }

    public SearchConfidence Confidence { get; set; } = null!;

    public List<ArticleSearchResult> Articles { get; set; } = new();
}

public class SearchConfidence
{
    public string Tier { get; set; } = null!;

    public double TopRrfScore { get; set; }

    public double? TopCosSim { get; set; }

    public int AgreementCount { get; set; }
}

public class ArticleSearchResult
{
    public long Id { get; set; }

    public string Title { get; set; } = null!;

    public string? Url { get; set; }

    public int OutletId { get; set; }

    public string OutletName { get; set; } = null!;

    public DateTime? PublishedAt { get; set; }

    public long? DenseRank { get; set; }

    public long? SparseRank { get; set; }

    public double? CosSim { get; set; }

    public double? TsScore { get; set; }

    public double RrfScore { get; set; }

    public int? ClusterId { get; set; }

    public int? SubClusterId { get; set; }

    public double? ScoreSensationalism { get; set; }

    public double? ScoreCitationQuality { get; set; }

    public double? ScoreRhetoricIntensity { get; set; }
}
