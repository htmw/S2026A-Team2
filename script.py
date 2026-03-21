from main import run_pipeline                                                                                                                                                                                    
                                                                                                                                                                                                                   
final = run_pipeline(                                                                                                                                                                                            
    source_type="csv",                                    
    source_config={"path": "datasets/coursea_data.csv"},
    target_db={
        "type": "sqlite",
        "path": "output/etl_output.db",
        "table": "courses",
        "if_exists": "replace"
    },
    user_instructions="drop rows where rating is null, normalize enrollment counts to integers. drop rows where course_title contains non-ASCII characters",
)
