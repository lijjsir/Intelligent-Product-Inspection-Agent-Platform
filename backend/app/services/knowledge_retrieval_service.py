from app.services.rag_retrieval_service import RagRetrievalService
from app.services.memory_service import MemoryService
from app.api.v1.memory_helpers import build_vector_service
from app.schemas.memory import MemorySearchRequest


class KnowledgeRetrievalService:
    def __init__(self,session,current):self.session,self.current=session,current

    async def search(self,query,top_k=8):
        rag=await RagRetrievalService(self.session,org_id=self.current.org_id,user_id=self.current.user_id,include_system=True).search_authorized(query=query,top_k=top_k)
        standards=[];references=[]
        for hit in rag.get("hits") or []:
            domain=hit.get("resource_domain") or (hit.get("payload") or {}).get("resource_domain")
            (standards if domain=="formal_standard" else references).append(hit)
        service=MemoryService(self.session,self.current.org_id,vector_service=build_vector_service(self.current.org_id,self.current.user_id))
        memory=await service.search(MemorySearchRequest(org_id=self.current.org_id,user_id=self.current.user_id,query=query,top_k=min(top_k,10),trace_id="knowledge-grouped-retrieval"))
        professional=[];legacy=[]
        for item in memory.items:
            # The service has already rechecked DB publication and provenance.
            row=await service._item_repo.get_by_memory_id(item.memory_id)
            target=professional if (row.content_json or {}).get("knowledge_admission_id") else legacy
            target.append(item.model_dump(mode="json"))
        return {"standards":standards,"professional_knowledge":professional,"reference_materials":references,"legacy_memory":legacy,
            "notice":"标准用于依据解释；已确认知识用于限定场景的专业参考；工作资料和旧记忆不能自动替代标准判定。"}
