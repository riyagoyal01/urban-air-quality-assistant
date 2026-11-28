import sys
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class ChatEndpointTests(unittest.TestCase):
    def test_chat_prompt_includes_current_dashboard_values(self):
        client = TestClient(main.app)
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content="PM2.5 is elevated.")
        )

        with patch.object(
            main, "call_ollama", return_value=ollama_response
        ) as ollama_call:
            response = client.post(
                "/api/chat",
                json={
                    "question": "Why is my PM2.5 level concerning?",
                    "pm2_5": 65.7,
                    "pm10": 69.4,
                    "ozone": 21.3,
                    "nitrogen_dioxide": 14.2,
                    "pm2_5_unit": "µg/m³",
                    "pm10_unit": "µg/m³",
                    "ozone_unit": "µg/m³",
                    "nitrogen_dioxide_unit": "µg/m³",
                    "household": "family_with_children",
                    "has_air_purifier": False,
                    "cooking_fuel": "wood",
                    "recommendations": [
                        {
                            "priority": "High",
                            "action": "Reduce outdoor activity",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "PM2.5 is elevated."})
        messages = ollama_call.call_args.args[0]
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        self.assertIn("PM2.5: 65.7", user_prompt)
        self.assertIn("PM2.5: 65.7 µg/m³", user_prompt)
        self.assertIn("PM10: 69.4", user_prompt)
        self.assertIn("Ozone: 21.3", user_prompt)
        self.assertIn("Nitrogen dioxide: 14.2", user_prompt)
        self.assertIn("family_with_children", user_prompt)
        self.assertIn("Air purifier available: No", user_prompt)
        self.assertIn("Cooking fuel: wood", user_prompt)
        self.assertIn("Reduce outdoor activity", user_prompt)
        self.assertIn('"priority": "High"', user_prompt)
        self.assertIn("Indoor pollutant measurements: not provided", user_prompt)
        self.assertIn("Never infer or estimate indoor pollutant concentrations", system_prompt)
        self.assertIn("do not invent actions", system_prompt)
        self.assertIn("using supplied dashboard readings", system_prompt)

    def test_chat_prompt_marks_missing_readings_as_not_provided(self):
        client = TestClient(main.app)
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content="Some readings were not provided.")
        )

        with patch.object(main, "call_ollama", return_value=ollama_response) as ollama_call:
            response = client.post(
                "/api/chat",
                json={
                    "question": "What are my current readings?",
                    "household": "family_with_children",
                    "has_air_purifier": False,
                    "cooking_fuel": "lpg",
                },
            )

        self.assertEqual(response.status_code, 200)
        user_prompt = ollama_call.call_args.args[0][1]["content"]
        self.assertIn("PM2.5: not provided", user_prompt)
        self.assertIn("PM10: not provided", user_prompt)

    def test_missing_units_are_not_replaced_by_hardcoded_units(self):
        client = TestClient(main.app)
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content="Some units were not provided.")
        )
        with patch.object(main, "call_ollama", return_value=ollama_response) as ollama_call:
            response = client.post("/api/chat", json={
                "question": "What is PM2.5?",
                "pm2_5": 65.7,
                "pm10": 69.4,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "pm2_5_unit": None,
                "pm10_unit": None,
            })
        self.assertEqual(response.status_code, 200)
        user_prompt = ollama_call.call_args.args[0][1]["content"]
        self.assertIn("PM2.5: 65.7\n", user_prompt)
        self.assertIn("PM10: 69.4\n", user_prompt)

    def test_multi_turn_history_is_sent_in_chronological_order(self):
        client = TestClient(main.app)
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content="The previous reading was elevated.")
        )
        history = [
            {"role": "user", "content": "What is PM2.5?"},
            {"role": "assistant", "content": "It is 65.7 ug/m3."},
            {"role": "user", "content": "Why does that matter?"},
        ]
        with patch.object(main, "call_ollama", return_value=ollama_response) as ollama_call:
            response = client.post("/api/chat", json={
                "question": "Can you explain what PM2.5 means?",
                "pm2_5": 65.7,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "recommendations": [],
                "history": history,
            })
        self.assertEqual(response.status_code, 200)
        messages = ollama_call.call_args.args[0]
        prior_roles = [message["role"] for message in messages if message["role"] in ("user", "assistant")]
        self.assertEqual(prior_roles, ["user", "user", "assistant", "user", "user"])
        contents = [message["content"] for message in messages]
        self.assertLess(contents.index("What is PM2.5?"), contents.index("It is 65.7 ug/m3."))
        self.assertLess(contents.index("It is 65.7 ug/m3."), contents.index("Why does that matter?"))
        self.assertEqual(messages[-1]["content"], "Can you explain what PM2.5 means?")

    def test_history_is_bounded_and_empty_or_invalid_entries_are_filtered(self):
        client = TestClient(main.app)
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content="A valid answer.")
        )
        history = [
            {"role": "assistant", "content": "valid prior answer"},
        ]
        history.extend(
            {"role": "user", "content": f"question {index}"}
            for index in range(19)
        )
        with patch.object(main, "call_ollama", return_value=ollama_response) as ollama_call:
            response = client.post("/api/chat", json={
                "question": "Latest question",
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "history": history,
            })
        self.assertEqual(response.status_code, 200)
        messages = ollama_call.call_args.args[0]
        history_messages = [item for item in messages if item["role"] in ("user", "assistant")]
        user_history = [
            item for item in history_messages
            if item["role"] == "user" and item["content"].startswith("question ")
        ]
        self.assertLessEqual(len(history_messages) - 2, 20)
        self.assertFalse(any(item["content"] == "  " for item in history_messages))
        self.assertIn("valid prior answer", [item["content"] for item in history_messages])
        self.assertEqual(len(user_history), 19)

    def test_requested_questions_receive_concise_style_and_household_context(self):
        examples = [
            ("What is my current PM2.5 level?", "Your modelled outdoor PM2.5 is 65.7 µg/m³."),
            ("Does my home have an air purifier?", "Yes, your household has an air purifier."),
            (
                "Does electric cooking mean my indoor air is completely clean?",
                "No. Electric cooking avoids fuel smoke, but cooking itself can still create particles.",
            ),
        ]
        client = TestClient(main.app)
        for question, answer in examples:
            with self.subTest(question=question):
                ollama_response = SimpleNamespace(
                    message=SimpleNamespace(content=answer)
                )
                with patch.object(
                    main, "call_ollama", return_value=ollama_response
                ) as ollama_call:
                    response = client.post(
                        "/api/chat",
                        json={
                            "question": question,
                            "pm2_5": 65.7,
                            "pm10": 69.4,
                            "ozone": 21.3,
                            "nitrogen_dioxide": 14.2,
                            "household": "family_with_children",
                            "has_air_purifier": True,
                            "cooking_fuel": "electricity",
                        },
                    )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["answer"], answer)
                messages = ollama_call.call_args.args[0]
                system_prompt = messages[0]["content"]
                user_prompt = messages[1]["content"]
                self.assertIn("1-3 sentences", system_prompt)
                self.assertIn("short prioritized bullet list", system_prompt)
                self.assertIn("Never invent AQI categories", system_prompt)
                self.assertIn("Cooking can generate particles with any fuel, including electricity", system_prompt)
                self.assertIn("PM2.5: 65.7", user_prompt)
                self.assertIn("PM10: 69.4", user_prompt)
                self.assertIn("Air purifier available: Yes", user_prompt)
                self.assertIn("Cooking fuel: electricity", user_prompt)

    def test_hypothetical_fuel_is_separate_from_actual_household_fuel(self):
        client = TestClient(main.app)
        answer = (
            "Hypothetically, electric cooking avoids fuel-combustion emissions, "
            "but cooking can still generate particles. Your household's selected "
            "fuel is LPG."
        )
        ollama_response = SimpleNamespace(
            message=SimpleNamespace(content=answer)
        )

        with patch.object(
            main, "call_ollama", return_value=ollama_response
        ) as ollama_call:
            response = client.post(
                "/api/chat",
                json={
                    "question": "Hypothetically, would electric cooking make my indoor air cleaner?",
                    "pm2_5": 65.7,
                    "pm10": 69.4,
                    "household": "family_with_children",
                    "has_air_purifier": False,
                    "cooking_fuel": "lpg",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], answer)
        messages = ollama_call.call_args.args[0]
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        self.assertIn("ACTUAL DASHBOARD CONTEXT", user_prompt)
        self.assertIn("Cooking fuel: lpg", user_prompt)
        self.assertIn("Treat any hypothetical preferences in the question as a scenario", user_prompt)
        self.assertIn("answer that scenario first", system_prompt)
        self.assertIn("Never infer or estimate indoor pollutant concentrations", system_prompt)

    def test_action_plan_preserves_dashboard_action_and_priority_without_ollama(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama") as ollama_call:
            response = client.post("/api/chat", json={
                "question": "What should my family do today?",
                "pm2_5": 65.7,
                "pm10": 69.4,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "recommendations": [
                    {
                        "category": "Outdoor activities",
                        "priority": "High",
                        "action": "Move children's outdoor play and exercise indoors.",
                        "reason": "PM2.5 is elevated.",
                    }
                ],
            })

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("Move children's outdoor play and exercise indoors.", answer)
        self.assertNotIn("move children outdoors", answer.lower())
        self.assertIn("High priority", answer)
        ollama_call.assert_not_called()

    def test_keep_windows_closed_recommendation_is_not_reversed(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama") as ollama_call:
            response = client.post("/api/chat", json={
                "question": "Should I open the windows?",
                "pm2_5": 65.7,
                "pm10": 69.4,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "recommendations": [
                    {
                        "category": "Indoor air",
                        "priority": "High",
                        "action": "Keep windows and doors closed.",
                        "reason": "Outdoor fine particles can enter indoors.",
                    }
                ],
            })

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("Keep windows and doors closed.", answer)
        ollama_call.assert_not_called()

    def test_missing_recommendations_do_not_invent_actions(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama") as ollama_call:
            response = client.post("/api/chat", json={
                "question": "What should my family do today?",
                "pm2_5": 65.7,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "recommendations": None,
            })

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("No dashboard recommendations are available", answer)
        self.assertIn("cannot", answer.lower())
        ollama_call.assert_not_called()

    def test_missing_priority_is_not_invented(self):
        client = TestClient(main.app)
        with patch.object(main, "call_ollama") as ollama_call:
            response = client.post("/api/chat", json={
                "question": "What should we do today?",
                "pm2_5": 65.7,
                "household": "family_with_children",
                "has_air_purifier": False,
                "cooking_fuel": "lpg",
                "recommendations": [
                    {"action": "Move children's outdoor play and exercise indoors."}
                ],
            })

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("Move children's outdoor play and exercise indoors.", answer)
        self.assertIn("Priority is not supplied", answer)
        self.assertNotIn("Critical priority", answer)
        ollama_call.assert_not_called()

    @unittest.skipUnless(os.getenv("LIVE_OLLAMA_TEST") == "1",
                         "Set LIVE_OLLAMA_TEST=1 to run the live Ollama check")
    def test_live_ollama_action_question_uses_authoritative_action(self):
        client = TestClient(main.app)
        response = client.post("/api/chat", json={
            "question": "What should my family do today?",
            "pm2_5": 65.7,
            "pm10": 69.4,
            "household": "family_with_children",
            "has_air_purifier": False,
            "cooking_fuel": "lpg",
            "recommendations": [
                {
                    "priority": "High",
                    "action": "Move children's outdoor play and exercise indoors.",
                }
            ],
        })

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("Move children's outdoor play and exercise indoors.", answer)
        self.assertNotIn("move children outdoors", answer.lower())


class ActionPlanIntentTests(unittest.TestCase):
    def test_factual_questions_are_not_misclassified_as_action_plans(self):
        for question in (
            "What does PM2.5 mean?",
            "What do these readings mean?",
            "What should PM2.5 be?",
            "What can cause high PM10?",
        ):
            with self.subTest(question=question):
                self.assertFalse(main.action_plan_question(question))

    def test_direct_action_plan_questions_are_recognized(self):
        for question in (
            "What should my family do today?",
            "What should we do?",
            "What can I do today?",
            "Can my children play outside?",
            "Show me the action plan",
        ):
            with self.subTest(question=question):
                self.assertTrue(main.action_plan_question(question))


if __name__ == "__main__":
    unittest.main()
