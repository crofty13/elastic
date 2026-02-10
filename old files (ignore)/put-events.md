
PUT /events
{
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