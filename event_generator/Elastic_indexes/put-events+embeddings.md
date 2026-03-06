### Step 1: Create the OpenAI model deployment
```
PUT _inference/text_embedding/my-openai-embeddings
{
  "service": "openai",
  "service_settings": {
    "api_key": "YOURKEYHERE",
    "model_id": "text-embedding-3-small"
  }
}
```
### Step 2: Deploy the pipeline
```
PUT _ingest/pipeline/events-embedding-pipeline
{
  "processors": [
    {
      "script": {
        "source": """
          def parts = [];
          if (ctx.name != null) parts.add('Name: ' + ctx.name);
          if (ctx.occasion != null) parts.add('Occasion: ' + ctx.occasion);
          if (ctx.season != null) parts.add('Season: ' + ctx.season);
          if (ctx.formality != null) parts.add('Formality: ' + ctx.formality);
          if (ctx.description != null) parts.add('Description: ' + ctx.description);
          if (ctx.dos != null) parts.add('Dos: ' + ctx.dos);
          if (ctx.donts != null) parts.add('Donts: ' + ctx.donts);
          if (ctx.fashion_trends_women?.current_trends != null) {
            parts.add('Women trends: ' + ctx.fashion_trends_women.current_trends);
          }
          if (ctx.fashion_trends_men?.current_trends != null) {
            parts.add('Men trends: ' + ctx.fashion_trends_men.current_trends);
          }
          ctx.combined_text = String.join('. ', parts);
        """
      }
    },
    {
      "inference": {
        "model_id": "my-openai-embeddings",
        "input_output": {
          "input_field": "combined_text",
          "output_field": "embedding"
        }
      }
    },
    {
      "set": {
        "field": "embedding_model",
        "value": "text-embedding-3-small"
      }
    }
  ]
}
```


### Step 3: Create the index with the pipeline
```
PUT /events
{
  "settings": {
    "default_pipeline": "events-embedding-pipeline"
  },
  "mappings": {
    "properties": {
      "description": {
        "type": "text"
      },
      "donts": {
        "type": "text"
      },
      "dos": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 1536,
        "index": true,
        "similarity": "cosine",
        "index_options": {
          "type": "bbq_hnsw",
          "m": 16,
          "ef_construction": 100,
          "rescore_vector": {
            "oversample": 3
          }
        }
      },
      "embedding_model": {
        "type": "keyword"
      },
      "event_id": {
        "type": "keyword"
      },
      "fashion_trends_men": {
        "properties": {
          "current_trends": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          },
          "recommended_accessories": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          }
        }
      },
      "fashion_trends_women": {
        "properties": {
          "current_trends": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          },
          "recommended_accessories": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword",
                "ignore_above": 256
              }
            }
          }
        }
      },
      "formality": {
        "type": "keyword"
      },
      "ideal_outfit_tags": {
        "properties": {
          "men": {
            "properties": {
              "formality": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              },
              "occasion": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              },
              "season": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              }
            }
          },
          "women": {
            "properties": {
              "formality": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              },
              "occasion": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              },
              "season": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              }
            }
          }
        }
      },
      "image_url": {
        "type": "keyword"
      },
      "location": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "occasion": {
        "type": "keyword"
      },
      "season": {
        "type": "keyword"
      },
      "type": {
        "type": "keyword"
      }
    }
  }
}
```

# Step 4 - Test document
```
PUT /events/_doc/1
{
  "event_id": "evt_001",
  "name": "Summer Garden Wedding",
  "occasion": "wedding",
  "season": "summer",
  "formality": "formal",
  "type": "outdoor",
  "location": "garden",
  "image_url": "https://example.com/images/summer-wedding.jpg",
  "description": "An elegant outdoor wedding ceremony held in a beautiful garden setting during warm summer months. Guests should dress formally while considering the outdoor venue and warm weather.",
  "dos": "Wear light, breathable fabrics like linen or cotton blends. Choose pastel or floral patterns. Bring sunglasses and consider a hat for sun protection. Opt for wedge heels or block heels that won't sink into grass.",
  "donts": "Avoid heavy fabrics like velvet or thick wool. Don't wear stiletto heels that will sink into the lawn. Avoid all-white outfits that might compete with the bride. Skip overly casual attire like sundresses or shorts.",
  "fashion_trends_women": {
    "current_trends": "Flowing maxi dresses in floral prints, midi-length wrap dresses, pastel-colored suits, statement fascinators, strappy sandals",
    "recommended_accessories": "Wide-brim sun hat, clutch purse, delicate jewelry, wedge heels or block heels, lightweight shawl for evening"
  },
  "fashion_trends_men": {
    "current_trends": "Light-colored linen suits, seersucker blazers, pastel dress shirts, bow ties, loafers without socks",
    "recommended_accessories": "Pocket square, sunglasses, leather belt, dress watch, panama hat"
  },
  "ideal_outfit_tags": {
    "women": {
      "occasion": "wedding guest formal garden outdoor",
      "season": "summer spring warm weather",
      "formality": "formal semi-formal cocktail"
    },
    "men": {
      "occasion": "wedding guest formal garden outdoor",
      "season": "summer spring warm weather",
      "formality": "formal semi-formal suit"
    }
  }
}
```