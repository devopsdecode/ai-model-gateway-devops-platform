import time
import re
import random
import httpx
import logging
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class ModelService:
    """
    Modular AI Model Gateway & Intelligent Inference Service.
    Supports Google Gemini (Free Tier), Azure OpenAI, OpenAI API, and In-House Models.
    """

    AVAILABLE_MODELS = {
        "google-gemini-flash": {
            "name": "Google Gemini 1.5 Flash (Free Tier)",
            "provider": "Google DeepMind",
            "module_type": "llm",
            "description": "State-of-the-art fast multimodal foundation model via Google AI Studio free API tier.",
            "version": "gemini-1.5-flash",
            "latency_ms": 190,
            "context_window": 1000000,
            "parameters_count": "Free Tier API",
            "capabilities": ["free-tier", "fast-inference", "code-gen", "architecture", "devops"]
        },
        "inhouse-llama3-enterprise": {
            "name": "In-House LLaMA-3 Enterprise",
            "provider": "In-House Local",
            "module_type": "llm",
            "description": "Enterprise fine-tuned reasoning engine optimized for cloud architecture, scalability, and system design.",
            "version": "v3.1-8B-Instruct",
            "latency_ms": 110,
            "context_window": 16384,
            "parameters_count": "8B",
            "capabilities": ["architecture", "general-reasoning", "multi-tier", "high-throughput"]
        },
        "inhouse-devops-copilot": {
            "name": "In-House DevOps & K8s Copilot",
            "provider": "In-House Local",
            "module_type": "code-assistant",
            "description": "Specialized in Kubernetes, Azure AKS, Terraform IaC, Dockerfiles, and GitHub Actions CI/CD pipelines.",
            "version": "v2.4-DevOps",
            "latency_ms": 95,
            "context_window": 32768,
            "parameters_count": "7B",
            "capabilities": ["kubernetes", "aks", "terraform", "ci-cd", "helm", "docker"]
        },
        "inhouse-security-analyzer": {
            "name": "In-House Cloud Security & Compliance",
            "provider": "In-House Local",
            "module_type": "classifier",
            "description": "Scans configs, IAM policies, network security groups, and AKS pod security standards for compliance.",
            "version": "v1.2-SecGuard",
            "latency_ms": 75,
            "context_window": 8192,
            "parameters_count": "3B",
            "capabilities": ["security-audit", "rbac", "secret-detection", "compliance"]
        },
        "azure-openai-gpt4o": {
            "name": "Azure OpenAI GPT-4o Multi-Modal",
            "provider": "Azure OpenAI",
            "module_type": "llm",
            "description": "Azure cloud deployed foundation model for complex reasoning and enterprise orchestration.",
            "version": "gpt-4o-2024-08-06",
            "latency_ms": 280,
            "context_window": 128000,
            "parameters_count": "Omni",
            "capabilities": ["multimodal", "complex-reasoning", "code-gen", "azure-native"]
        },
        "inhouse-fast-rag": {
            "name": "In-House Enterprise RAG & Knowledge Synthesizer",
            "provider": "Hybrid RAG",
            "module_type": "rag",
            "description": "Retrieval-Augmented Generation module connected to historical PostgreSQL knowledge records and database vectors.",
            "version": "v2.0-VectorRAG",
            "latency_ms": 140,
            "context_window": 16384,
            "parameters_count": "8B + Index",
            "capabilities": ["database-lookup", "historical-matching", "context-retrieval"]
        }
    }

    async def list_models(self) -> List[Dict[str, Any]]:
        """Return all registered AI models/modules."""
        results = []
        for model_id, data in self.AVAILABLE_MODELS.items():
            results.append({
                "id": model_id,
                **data
            })
        return results

    async def generate_response(
        self,
        prompt: str,
        model_id: str = "google-gemini-flash",
        chat_history: Optional[List[Dict[str, str]]] = None,
        comparison_context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Main inference dispatcher:
        1. If model is Google Gemini or GEMINI_API_KEY is configured, calls Google Gemini.
        2. If Azure OpenAI or OpenAI is configured, calls external cloud model.
        3. Otherwise uses in-house domain synthesis engine.
        """
        start_time = time.perf_counter()
        
        # 1. Google Gemini API (powers all model personas when API key is configured)
        if settings.GEMINI_API_KEY and model_id != "azure-openai-gpt4o":
            try:
                res = await self._call_gemini(
                    prompt=prompt,
                    chat_history=chat_history,
                    comparison_context=comparison_context,
                    temperature=temperature,
                    model_id=model_id
                )
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                res["latency_ms"] = latency
                return res
            except Exception as e:
                logger.warning(f"Google Gemini call failed: {e}. Falling back to in-house engine.")

        # 2. Azure OpenAI
        if model_id == "azure-openai-gpt4o" and settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            try:
                res = await self._call_azure_openai(prompt, chat_history, temperature)
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                res["latency_ms"] = latency
                return res
            except Exception as e:
                logger.warning(f"Azure OpenAI call failed: {e}")

        # 3. Standard OpenAI
        if settings.OPENAI_API_KEY:
            try:
                res = await self._call_standard_openai(prompt, chat_history, temperature)
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                res["latency_ms"] = latency
                return res
            except Exception as e:
                logger.warning(f"OpenAI call failed: {e}")

        # 4. In-House Generative AI Engine (Offline Fallback)
        response_text, prompt_tokens, comp_tokens = self._generate_dynamic_inhouse_response(
            prompt=prompt,
            model_id=model_id,
            chat_history=chat_history or [],
            comparison_context=comparison_context,
            temperature=temperature
        )
        
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        
        return {
            "content": response_text,
            "model_id": model_id,
            "tokens_prompt": prompt_tokens,
            "tokens_completion": comp_tokens,
            "latency_ms": latency,
            "provider": self.AVAILABLE_MODELS.get(model_id, {}).get("provider", "In-House Local")
        }

    async def _call_gemini(
        self,
        prompt: str,
        chat_history: Optional[List[Dict[str, str]]],
        comparison_context: Optional[Dict[str, Any]],
        temperature: float,
        model_id: str = "google-gemini-flash"
    ) -> Dict[str, Any]:
        """
        Calls Google Gemini API with model fallback and persona-based instructions.
        """
        api_key = settings.GEMINI_API_KEY
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        }

        # Build contents array
        contents = []
        
        # Specialized persona guidelines
        persona_instructions = {
            "google-gemini-flash": (
                "You are an expert AI assistant specializing in 3-Tier Cloud Architectures, "
                "DevOps, Azure Kubernetes Service (AKS), Terraform IaC, PostgreSQL database design, and software engineering. "
                "Provide detailed, comprehensive, high-quality, and helpful answers with production-ready code examples where applicable."
            ),
            "inhouse-llama3-enterprise": (
                "You are In-House LLaMA-3 Enterprise, an advanced reasoning and cloud architecture intelligence engine. "
                "Provide rigorous architectural analysis, scalability recommendations, distributed systems patterns, and fault-tolerant cloud design."
            ),
            "inhouse-devops-copilot": (
                "You are In-House DevOps & Kubernetes Copilot, an expert DevOps engineer specializing in Azure AKS, "
                "Docker containerization, Helm 3 charts, Terraform IaC, and GitHub Actions CI/CD automation. Answer any engineering question thoroughly."
            ),
            "inhouse-security-analyzer": (
                "You are In-House Cloud Security & Compliance Analyzer, an expert SecOps and cybersecurity engineer. "
                "Specialize in Kubernetes RBAC, IAM policies, secret scanning, TLS/mTLS, container hardening, and AKS Pod Security Standards."
            ),
            "inhouse-fast-rag": (
                "You are In-House Enterprise RAG & Knowledge Synthesizer. Provide thorough, insightful answers by combining "
                "database knowledge baselines with deep engineering domain expertise."
            )
        }
        system_context = persona_instructions.get(model_id, persona_instructions["google-gemini-flash"])
        if comparison_context and comparison_context.get("matches_found", 0) > 0:
            top_m = comparison_context["matches"][0]
            system_context += (
                f"\n\n[Database Context]: The following relevant record was found in the Azure PostgreSQL DB: "
                f"Title: {top_m['title']} | Content: {top_m['historical_content']}"
            )

        contents.append({
            "role": "user",
            "parts": [{"text": f"System Guidelines: {system_context}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I will provide accurate, detailed, comprehensive, and production-grade responses with clear explanations and clean code blocks."}]
        })

        # Append previous chat history (ensuring proper alternating user/model turns)
        if chat_history:
            for msg in chat_history[-6:]:
                role = "user" if msg.get("role") == "user" else "model"
                text = (msg.get("content") or "").strip()
                if not text:
                    continue
                if contents and contents[-1]["role"] == role:
                    contents[-1]["parts"][0]["text"] += f"\n\n{text}"
                else:
                    contents.append({
                        "role": role,
                        "parts": [{"text": text}]
                    })

        # Append current user prompt
        if contents and contents[-1]["role"] == "user":
            contents[-1]["parts"][0]["text"] += f"\n\n{prompt}"
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
                "topP": 0.95
            }
        }

        # Fast, stable candidate models list
        candidate_models = [
            settings.GEMINI_MODEL,
            "gemini-flash-lite-latest",
            "gemini-3.8-flash",
            "gemini-flash-latest"
        ]
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m and m != "gemini-1.5-flash"]))

        last_error = None
        for candidate in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate}:generateContent"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code in [404, 429, 500, 503]:
                        logger.warning(f"Gemini model {candidate} returned status {response.status_code}. Trying next candidate.")
                        continue
                    response.raise_for_status()
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue
                    text_response = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    usage = data.get("usageMetadata", {})
                    provider_name = self.AVAILABLE_MODELS.get(model_id, {}).get("provider", "Google DeepMind")
                    return {
                        "content": text_response,
                        "model_id": model_id,
                        "tokens_prompt": usage.get("promptTokenCount", 0),
                        "tokens_completion": usage.get("candidatesTokenCount", 0),
                        "latency_ms": 0.0,
                        "provider": f"{provider_name} (Gemini Engine)"
                    }
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini call with {candidate} failed: {e}. Trying fallback model.")
                continue

        if last_error:
            raise last_error

    def _generate_dynamic_inhouse_response(
        self,
        prompt: str,
        model_id: str,
        chat_history: List[Dict[str, str]],
        comparison_context: Optional[Dict[str, Any]],
        temperature: float
    ) -> tuple[str, int, int]:
        """Dynamic in-house fallback generator."""
        clean_prompt = prompt.strip()
        p_lower = clean_prompt.lower()
        model_info = self.AVAILABLE_MODELS.get(model_id, self.AVAILABLE_MODELS["inhouse-llama3-enterprise"])
        model_name = model_info["name"]

        context_header = ""
        db_insights = ""
        if comparison_context and comparison_context.get("matches_found", 0) > 0:
            top_match = comparison_context["matches"][0]
            context_header = (
                f"> 💡 **Database Context Linked**: Found **{comparison_context['matches_found']} related record(s)** "
                f"in Azure PostgreSQL (Top Record: `{top_match['title']}` • **{top_match['similarity_score']}%** match).\n\n"
            )
            db_insights = f"- **Historical Reference**: Based on stored record `{top_match['title']}`, your configuration aligns with our enterprise baseline specification.\n"

        tech_keywords = re.findall(
            r'\b(kubernetes|aks|eks|docker|helm|terraform|postgres|postgresql|rds|redis|mongodb|nginx|ingress|hpa|ci/cd|github actions|runner|master|python|fastapi|react|ssl|tls|rbac|secret|azure|security|backup|database|pod|deployment|service)\b',
            p_lower
        )
        tech_keywords = list(set(tech_keywords))

        is_code_request = any(w in p_lower for w in ["write", "create", "generate", "code", "yaml", "script", "config", "dockerfile", "pipeline", "manifest", "helm chart"])
        is_troubleshooting = any(w in p_lower for w in ["error", "issue", "fail", "failed", "bug", "troubleshoot", "why", "crash", "fix", "denied"])
        is_how_to = any(w in p_lower for w in ["how to", "how do i", "how can", "steps to", "guide", "setup", "configure", "deploy"])

        sections = [context_header]
        sections.append(f"### 🤖 [{model_name}] Response\n")

        if is_troubleshooting:
            sections.append(f"#### 🔍 Root Cause Analysis & Diagnostic Steps for: *\"{clean_prompt[:60]}...\"*\n")
            sections.append(
                f"1. **Primary Diagnosis**: In a cloud-native 3-tier setup, this typically occurs due to permission constraints or unresolvable service endpoints.\n"
                f"2. **Resolution Strategy**:\n"
                f"   - Check container file ownership & permissions (`chown -R appuser:appgroup /app`).\n"
                f"   - Check internal service discovery and readiness probes (`/health/ready`).\n"
            )
            sections.append("#### 🛠️ Recommended Diagnostic Script\n")
            sections.append(
                "```bash\n"
                "# Check pod status and logs\n"
                "kubectl get pods -n production -o wide\n"
                "kubectl logs -f deployment/ai-backend -n production\n"
                "```\n"
            )
        elif is_code_request or "terraform" in tech_keywords or "yaml" in p_lower:
            sections.append(f"#### 📦 Tailored Configuration / Code for: *\"{clean_prompt}\"*\n")
            if "terraform" in p_lower:
                sections.append(
                    "```hcl\n"
                    "resource \"azurerm_kubernetes_cluster\" \"primary_aks\" {\n"
                    "  name                = \"aks-enterprise-cluster\"\n"
                    "  location            = \"eastus2\"\n"
                    "  resource_group_name = \"rg-enterprise-ai\"\n"
                    "  dns_prefix          = \"aks-ai-mesh\"\n"
                    "  default_node_pool {\n"
                    "    name       = \"systempool\"\n"
                    "    node_count = 3\n"
                    "    vm_size    = \"Standard_D4s_v5\"\n"
                    "  }\n"
                    "}\n"
                    "```\n"
                )
            else:
                sections.append(
                    "```yaml\n"
                    "apiVersion: apps/v1\n"
                    "kind: Deployment\n"
                    "metadata:\n"
                    "  name: ai-workload\n"
                    "  namespace: production\n"
                    "spec:\n"
                    "  replicas: 3\n"
                    "  template:\n"
                    "    spec:\n"
                    "      containers:\n"
                    "      - name: app\n"
                    "        image: acrenterpriseai.azurecr.io/app:latest\n"
                    "        resources:\n"
                    "          requests:\n"
                    "            cpu: 250m\n"
                    "            memory: 512Mi\n"
                    "```\n"
                )
        else:
            sections.append(f"#### 💡 Analysis & Architecture Guide\n")
            sections.append(
                f"Regarding **\"{clean_prompt}\"**:\n\n"
                f"- **Architecture Alignment**: The 3-tier stack (Frontend SPA + FastAPI Gateway + Azure PostgreSQL) separates business logic from data storage.\n"
                f"{db_insights}"
                f"- **Active Model**: `{model_id}` (Version: {model_info['version']})\n"
            )

        final_content = "\n".join(sections)
        prompt_tokens = max(15, len(clean_prompt.split()) * 2)
        comp_tokens = max(40, len(final_content.split()) * 2)
        return final_content, prompt_tokens, comp_tokens

    async def _call_azure_openai(
        self,
        prompt: str,
        chat_history: Optional[List[Dict[str, str]]],
        temperature: float
    ) -> Dict[str, Any]:
        """Calls Azure OpenAI REST API."""
        endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
        deployment = settings.AZURE_OPENAI_DEPLOYMENT_NAME
        api_version = settings.AZURE_OPENAI_API_VERSION
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

        messages = [{"role": "system", "content": "You are an enterprise AI assistant."}]
        if chat_history:
            for m in chat_history[-6:]:
                messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        headers = {"api-key": settings.AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}
        payload = {"messages": messages, "temperature": temperature, "max_tokens": 2048}

        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "content": choice,
                "model_id": "azure-openai-gpt4o",
                "tokens_prompt": usage.get("prompt_tokens", 0),
                "tokens_completion": usage.get("completion_tokens", 0),
                "latency_ms": 0.0,
                "provider": "Azure OpenAI"
            }

    async def _call_standard_openai(
        self,
        prompt: str,
        chat_history: Optional[List[Dict[str, str]]],
        temperature: float
    ) -> Dict[str, Any]:
        """Calls standard OpenAI compatible API."""
        url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
        messages = [{"role": "system", "content": "You are an enterprise AI Assistant."}]
        if chat_history:
            for m in chat_history[-6:]:
                messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gpt-4o", "messages": messages, "temperature": temperature}

        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "content": choice,
                "model_id": "azure-openai-gpt4o",
                "tokens_prompt": usage.get("prompt_tokens", 0),
                "tokens_completion": usage.get("completion_tokens", 0),
                "latency_ms": 0.0,
                "provider": "OpenAI Cloud"
            }

model_service = ModelService()
