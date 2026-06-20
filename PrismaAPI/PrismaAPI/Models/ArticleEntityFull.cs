using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("article_entities_full")]
public class ArticleEntityFull
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Column("article_id")]
    public int ArticleId { get; set; }

    [Required]
    [MaxLength(255)]
    [Column("entity_text")]
    public string EntityText { get; set; } = string.Empty;

    [Required]
    [MaxLength(20)]
    [Column("entity_label")]
    public string EntityLabel { get; set; } = string.Empty;
}
