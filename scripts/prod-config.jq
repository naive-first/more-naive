if all([env.DB_DATABASE, env.DB_USERNAME, env.DB_PASSWORD][]; type == "string" and test("\\S")) then
  {apiVersion: "v1", kind: "List", items: [
    {apiVersion: "v1", kind: "ConfigMap",
     metadata: {name: "more-naive-config", namespace: env.NAMESPACE},
     data: {DB_DATABASE: env.DB_DATABASE, DB_USERNAME: env.DB_USERNAME,
            DB_URL: ("jdbc:postgresql://postgres." + env.NAMESPACE + ".svc.cluster.local:5432/" + (env.DB_DATABASE | @uri))}},
    {apiVersion: "v1", kind: "Secret", type: "Opaque",
     metadata: {name: "more-naive-db", namespace: env.NAMESPACE},
     data: {DB_PASSWORD: (env.DB_PASSWORD | @base64)}}
  ]}
else error("DB_DATABASE, DB_USERNAME and DB_PASSWORD are required") end
