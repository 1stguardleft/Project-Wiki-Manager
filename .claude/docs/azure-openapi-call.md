LLM Gateway API 키

로컬 개발 환경(Python SDK, curl 등)에서 Azure OpenAI 리소스를 안전하게 사용할 수 있는 개인 API 키를 관리합니다. 유효기간은 본인이 속한 마스터프로젝트 기수의 종료일까지 자동 설정됩니다.
+ 새 API 키 발급
이름	키	상태	발급일	마지막 사용	만료	
lstguardleft-api-key	atl-C6QIit7z********	활성	2026. 05. 27. 오후 03:27	-	2026. 05. 29. 오후 11:59	폐기
엔드포인트 정보
Base URL	https://skax.ai-talentlab.com복사
API 경로	/openai/deployments/{deployment}/chat/completions 등 (Azure OpenAI 와 동일)
api-version	2024-12-01-preview복사
인증 헤더	api-key: atl-... 또는 Authorization: Bearer atl-...
허용 모델	
gpt-4.1
gpt-4.1-mini
gpt-4o
gpt-4o-mini
gpt-5
gpt-5-mini
gpt-5.4
text-embedding-3-large
text-embedding-3-small
text-embedding-ada-002
위 이름을 그대로 model 파라미터(또는 경로의 {deployment})에 사용하세요. 칩에 마우스를 올리면 실제 AOAI deployment 이름을 확인할 수 있습니다.
예제 코드
Python — openai (AzureOpenAI)
Python — 스트리밍
Python — Embeddings
curl
코드 복사
from openai import AzureOpenAI

client = AzureOpenAI(
    azure_endpoint="https://skax.ai-talentlab.com",
    api_key="atl-...",            # 발급받은 키
    api_version="2024-12-01-preview",
)

resp = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "안녕"}],
)
print(resp.choices[0].message.content)
⚠️ 발급된 키는 본인만 사용하세요. 외부(깃허브, 채팅 등)에 노출된 경우 즉시 폐기 후 재발급하세요.