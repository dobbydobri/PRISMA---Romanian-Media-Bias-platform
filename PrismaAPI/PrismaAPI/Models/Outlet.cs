using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("outlets")]
public class Outlet
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Required]
    [MaxLength(100)]
    [Column("name")]
    public string Name { get; set; } = string.Empty;

    [Required]
    [MaxLength(50)]
    [Column("outlet_type")]
    public string OutletType { get; set; } = string.Empty;

    [MaxLength(255)]
    [Column("base_url")]
    public string? BaseUrl { get; set; }

    [Column("created_at", TypeName = "timestamptz")]
    public DateTime? CreatedAt { get; set; }


    public ICollection<Article> Articles { get; set; } = new List<Article>();

    public ICollection<FactCheck> FactChecks { get; set; } = new List<FactCheck>();
}
