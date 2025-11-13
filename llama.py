from transformers import AutoModelForCausalLM, AutoTokenizer

# Replace this with the model you want — for example:
# "meta-llama/Llama-3-8b" or "meta-llama/Llama-2-7b-chat-hf"
model_name = "meta-llama/Llama-3.2-1B"

# Load tokenizer and model
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",          # Automatically selects fp16/bf16 if available
    device_map="auto"            # Automatically places layers on GPU(s)
)

prompt = "Explain quantum computing in simple terms:"

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(
    **inputs,
    max_new_tokens=150,
    temperature=0.7,
    top_p=0.9,
)

print(tokenizer.decode(outputs[0], skip_special_tokens=True))
