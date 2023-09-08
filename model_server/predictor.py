from transformers import AutoModelForCausalLM, AutoTokenizer
import torch


class Predictor:
    def __init__(self, path: str):
        self.model = torch.compile(
            AutoModelForCausalLM.from_pretrained(path),
            mode="max-autotune",
        )
        self.tokenizer = AutoTokenizer.from_pretrained("tinkoff-ai/ruDialoGPT-medium")

        self.first = " @@ПЕРВЫЙ@@ "
        self.second = " @@ВТОРОЙ@@ "

    def add_tokens(self, conversation: list[str]):
        if not conversation:
            return f"{self.second} "

        res = ""
        length = len(conversation)
        for index, phrase in enumerate(conversation):
            res += (self.first if (length - index) % 2 else self.second) + phrase

        return res.strip() + self.second

    def predict(self, message: list[str]) -> list[str]:
        inputs = self.tokenizer(
            self.add_tokens(message),
            return_tensors="pt",
        )
        generated_token_ids = self.model.generate(
            **inputs,
            top_k=20,  # sample one of k most likely
            top_p=0.9,  # sample from those most likely which sum >= p
            num_beams=20,  # num beams for beam search
            num_return_sequences=3,  # how many candidates to return
            do_sample=True,  # do sample or greedy search
            no_repeat_ngram_size=2,  # n grams of this n must not repeat in a text
            temperature=1.5,  # make this value higher to get more interesting responses
            # repetition_penalty=2.0,  # make this value higher to fight with repetition
            length_penalty=-0.5,  # < 1 for short texts, > 1 for long
            eos_token_id=50257,  # when to stop
            pad_token_id=self.tokenizer.eos_token_id,
            max_new_tokens=60,  # how many tokens to generate
        )

        return [
            self.tokenizer.decode(tokens)
            .split("@@ВТОРОЙ@@")[-1]
            .split("@@ПЕРВЫЙ@@")[0]
            .strip()
            for tokens in generated_token_ids
        ]


if __name__ == "__main__":
    pred = Predictor("model/output")
    print(
        *pred.predict(
            [
                "Ограничения - удел ограниченных.....",
            ]
        ),
        sep="\n\n",
    )
