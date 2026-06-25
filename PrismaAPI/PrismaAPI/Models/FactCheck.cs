using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("fact_checks")]
public class FactCheck
{
    [Key]
    [Column("id")]
    public long Id { get; set; }

    [Column("article_id")]
    public long ArticleId { get; set; }

    [Column("outlet_id")]
    public int OutletId { get; set; }

    [Required]
    [MaxLength(30)]
    [Column("verdict")]
    public string Verdict { get; set; } = string.Empty;

    [Required]
    [MaxLength(20)]
    [Column("verdict_type")]
    public string VerdictType { get; set; } = string.Empty;

    [Column("claim_text")]
    public string? ClaimText { get; set; }

    [MaxLength(255)]
    [Column("raw_verdict")]
    public string? RawVerdict { get; set; }

    [Column("published_at")]
    public DateTime? PublishedAt { get; set; }

    [Column("created_at")]
    public DateTime? CreatedAt { get; set; }

    [Column("severity_score")]
    public short? SeverityScore { get; set; }


    public Article Article { get; set; } = null!;

    public Outlet Outlet { get; set; } = null!;
}
