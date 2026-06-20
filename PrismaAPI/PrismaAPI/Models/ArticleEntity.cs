using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("article_entities")]
public class ArticleEntity
{
    [Key]
    [Column("id")]
    public long Id { get; set; }

    [Column("article_id")]
    public long ArticleId { get; set; }

    [Required]
    [MaxLength(255)]
    [Column("entity_text")]
    public string EntityText { get; set; } = string.Empty;

    [Required]
    [MaxLength(20)]
    [Column("entity_label")]
    public string EntityLabel { get; set; } = string.Empty;

    [Column("created_at")]
    public DateTime? CreatedAt { get; set; }


    public Article Article { get; set; } = null!;
}
