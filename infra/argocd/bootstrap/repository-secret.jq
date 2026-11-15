{
  apiVersion: "v1", kind: "Secret",
  metadata: {name: "more-naive-repository", namespace: "argocd",
             labels: {"argocd.argoproj.io/secret-type": "repository"}},
  data: ({type: "git", url: "https://github.com/naive-first/more-naive.git",
          username: ((env.ARGO_REPO_USERNAME // "") | if length > 0 then . else "x-access-token" end),
          password: env.ARGO_REPO_TOKEN} | with_entries(.value |= @base64))
}
