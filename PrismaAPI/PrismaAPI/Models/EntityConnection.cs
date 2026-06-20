using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("entity_connections")]
public class EntityConnection
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Required]
    [MaxLength(255)]
    [Column("source_entity")]
    public string SourceEntity { get; set; } = string.Empty;

    [Required]
    [MaxLength(50)]
    [Column("source_label")]
    public string SourceLabel { get; set; } = string.Empty;

    [Required]
    [MaxLength(255)]
    [Column("target_entity")]
    public string TargetEntity { get; set; } = string.Empty;

    [Required]
    [MaxLength(50)]
    [Column("target_label")]
    public string TargetLabel { get; set; } = string.Empty;

    [Column("weight_raw")]
    public int WeightRaw { get; set; }

    [Column("weight_pmi")]
    public double WeightPmi { get; set; }
}
