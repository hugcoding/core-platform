import json
import unittest
from unittest.mock import patch

from core.semantic.rag import (
    GenerationRequest, OpenAICompatibleLocalProvider, abstention,
    build_prompts, render_markdown, validate_answer,
)


SOURCES = [{
    "source_id": "S1", "filename": "bron.docx", "chunk_ordinal": 0,
    "text": "Python wordt voor datapipelines gebruikt.",
}]


class SemanticRagTests(unittest.TestCase):
    def test_prompt_contains_source_and_version(self):
        system, user = build_prompts("Waarvoor wordt Python gebruikt?", SOURCES)
        self.assertIn("uitsluitend", system)
        self.assertIn("scrum-59-rag-v1", user)
        self.assertIn("SOURCE S1", user)
        self.assertIn(SOURCES[0]["text"], user)

    def test_valid_grounded_answer_is_accepted(self):
        content = json.dumps({
            "answer": "Python wordt hiervoor gebruikt [S1].", "abstained": False,
            "citations": ["S1"], "confidence": "high", "reason": "bronbewijs",
        })
        answer = validate_answer(content, SOURCES)
        self.assertFalse(answer["abstained"])
        self.assertEqual(answer["citations"], ["S1"])

    def test_missing_or_unknown_citation_forces_abstention(self):
        missing = validate_answer(json.dumps({
            "answer": "Een antwoord", "abstained": False, "citations": [],
            "confidence": "high",
        }), SOURCES)
        unknown = validate_answer(json.dumps({
            "answer": "Een antwoord [S2]", "abstained": False, "citations": ["S2"],
            "confidence": "high",
        }), SOURCES)
        self.assertEqual(missing, abstention("missing_citations"))
        self.assertEqual(unknown, abstention("unknown_citation"))

    def test_invalid_json_forces_abstention(self):
        self.assertEqual(
            validate_answer("geen json", SOURCES),
            abstention("provider_response_not_valid_json"),
        )

    def test_markdown_has_citations_but_not_raw_source_text(self):
        report = {
            "status": "completed", "prompt_version": "scrum-59-rag-v1",
            "read_only": True, "query": "vraag",
            "answer": {"answer": "Antwoord [S1]", "confidence": "high", "abstained": False},
            "sources": [{
                **SOURCES[0], "file_id": 42, "path": "/volume1/bron.docx",
                "ranking_score": 0.8,
            }],
        }
        markdown = render_markdown(report)
        self.assertIn("[S1]", markdown)
        self.assertIn("file_id `42`", markdown)
        self.assertNotIn(SOURCES[0]["text"], markdown)

    def test_provider_rejects_public_endpoint(self):
        with self.assertRaisesRegex(ValueError, "local"):
            OpenAICompatibleLocalProvider("https://api.example.com/v1")

    @patch("core.semantic.rag.urlopen")
    def test_provider_contract_is_openai_compatible(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps({
            "model": "local-model", "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 10},
        }).encode()
        provider = OpenAICompatibleLocalProvider("http://192.168.1.20:11434/v1")
        result = provider.generate(GenerationRequest("local-model", "system", "user"))
        self.assertEqual(result["model"], "local-model")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0.0)


if __name__ == "__main__":
    unittest.main()
