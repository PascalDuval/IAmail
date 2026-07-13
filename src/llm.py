from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from ollama import Client


@dataclass
class LLMResponse:
	content: str
	model: str
	host: str


class OllamaLLM:
	def __init__(self, model: str = "mistral", host: str = "http://localhost:11434") -> None:
		self.model = model
		self.host = host
		self.client = Client(host=host)

	@classmethod
	def from_env(cls) -> "OllamaLLM":
		load_dotenv()
		model = os.getenv("LLM_MODEL", "mistral").strip() or "mistral"
		host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip() or "http://localhost:11434"
		return cls(model=model, host=host)

	def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> LLMResponse:
		response: dict[str, Any] = self.client.chat(
			model=self.model,
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			options={"temperature": temperature},
		)

		message = response.get("message", {})
		content = str(message.get("content", "")).strip()
		return LLMResponse(content=content, model=self.model, host=self.host)

	def generate_answer(self, question: str, context: str) -> str:
		system_prompt = (
			"Tu es un assistant francais expert en analyse de mails. "
			"Tu dois repondre uniquement a partir du contexte fourni. "
			"Si le contexte est insuffisant, dis-le explicitement. "
			"Sois concis, precis, et en francais avec accents."
		)
		user_prompt = (
			f"Question: {question}\n\n"
			f"Contexte:\n{context}\n\n"
			"Reponse attendue: une reponse courte, factuelle, sans inventer de donnees."
		)

		try:
			response = self.chat(system_prompt=system_prompt, user_prompt=user_prompt)
			if response.content:
				return response.content
		except Exception:
			pass

		return _fallback_answer(question, context)


def _fallback_answer(question: str, context: str) -> str:
	lines = [line.strip() for line in context.splitlines() if line.strip()]
	if not lines:
		return f"Aucune information exploitable n'a ete trouvee pour: {question}"

	return "\n".join(lines[:6])
