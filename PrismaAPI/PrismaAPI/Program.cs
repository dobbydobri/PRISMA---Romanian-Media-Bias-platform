using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Npgsql;
using PrismaAPI.Configuration;
using PrismaAPI.Data;
using PrismaAPI.Services;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAngular", policy =>
    {
        policy.WithOrigins("http://localhost:4200")
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
        options.JsonSerializerOptions.DefaultIgnoreCondition = 
            System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull;
    });

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    var xmlFilename = $"{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}.xml";
    var xmlPath = Path.Combine(AppContext.BaseDirectory, xmlFilename);
    if (File.Exists(xmlPath))
    {
        options.IncludeXmlComments(xmlPath);
    }
});

builder.Services.AddDbContext<PrismaDbContext>(options =>
{
    options.UseNpgsql(
        builder.Configuration.GetConnectionString("DefaultConnection"),
        npgsqlOptions => npgsqlOptions.UseVector()
    );
    options.UseQueryTrackingBehavior(QueryTrackingBehavior.NoTracking);
});

builder.Services.AddNpgsqlDataSource(
    builder.Configuration.GetConnectionString("DefaultConnection")!);

builder.Services.Configure<SearchOptions>(
    builder.Configuration.GetSection(SearchOptions.Section));

builder.Services.AddHttpClient("EmbeddingService", client =>
{
    var baseUrl = builder.Configuration["EmbeddingService:BaseUrl"] ?? "http://localhost:5001";
    client.BaseAddress = new Uri(baseUrl);
    client.Timeout = TimeSpan.FromSeconds(30);
});

builder.Services.AddHttpClient("QueryEmbedder", (sp, client) =>
{
    var opts = sp.GetRequiredService<IOptions<SearchOptions>>().Value;
    client.BaseAddress = new Uri(opts.EmbedderBaseUrl);
    client.Timeout = TimeSpan.FromMilliseconds(opts.EmbedderTimeoutMs);
});

builder.Services.AddScoped<OutletService>();
builder.Services.AddScoped<ArticleService>();
builder.Services.AddScoped<ClusterService>();
builder.Services.AddScoped<ClusterRunWindowService>();
builder.Services.AddScoped<FactCheckService>();
builder.Services.AddScoped<AnalysisService>();
builder.Services.AddScoped<ISearchService, SearchService>();
builder.Services.AddScoped<ConnectionsService>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI(options =>
    {
        options.SwaggerEndpoint("/swagger/v1/swagger.json", "PrismaAPI v1");
        options.RoutePrefix = "swagger";
    });
}

app.UseCors("AllowAngular");

app.MapControllers();

app.Run();
