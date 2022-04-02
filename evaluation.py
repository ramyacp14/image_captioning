import torch
import torch.nn as nn
import torch.nn.functional as F
import time
import PIL
from transformers import BertTokenizer
from tqdm import tqdm
import time
import os
import json
from utils import configs, transform, metric_scores
from models import ImageCaptionModel
from datasets import ImageCaptionDataset


def preprocess_image(image_path, transform):
    """
    This function will preprocess image
    """
    image = PIL.Image.open(image_path).convert("RGB")
    image = transform(image)
    image = image.unsqueeze(0)
    return image

def generate_caption(model, image, tokenizer, max_seq_len=256, beam_size=3, device=torch.device("cpu"), print_process=False):
    """
    This funciton will generate caption for an image
    """
    image = image.to(device)
    # Generate caption
    with torch.no_grad():
        # Feed forward Encoder
        encoder_output = model.encoder(image)
        # Initialize beam list
        beams = [([tokenizer.bos_token_id], 0)]
        completed = []
        # Start decoding
        for _ in range(max_seq_len):
            new_beams = []
            for beam in beams:
                # Get input token
                input_token = torch.tensor([beam[0]]).to(device)
                # Create mask
                target_mask = model.make_mask(input_token).to(device)
                # Decoder forward pass
                pred = model.decoder(input_token, encoder_output, target_mask)
                # Forward to linear classify token in vocab and Softmax
                pred = F.softmax(model.fc(pred), dim=-1)
                # Get tail predict token
                pred = pred[:, -1, :].view(-1)
                # Get top k tokens
                top_k_scores, top_k_tokens = pred.topk(beam_size)
                # Update beams
                for i in range(beam_size):
                    new_beams.append((beam[0] + [top_k_tokens[i].item()], beam[1] + top_k_scores[i].item()))
            
            import copy
            beams = copy.deepcopy(new_beams)
            # Sort beams by score
            beams = sorted(beams, key=lambda x: x[1], reverse=True)[:beam_size]
            # Add completed beams to completed list and reduce beam size
            for beam in beams:
                if beam[0][-1] == tokenizer.eos_token_id:
                    completed.append(beam)
                    beams.remove(beam)
                    beam_size -= 1
            
            # Print screen progress
            if print_process:
                print(f"Step {_+1}/{max_seq_len}")
                print(f"Beam size: {beam_size}")
                print(f"Beams: {[tokenizer.decode(beam[0]) for beam in beams]}")
                print(f"Completed beams: {[tokenizer.decode(beam[0]) for beam in completed]}")
                print(f"Beams score: {[beam[1] for beam in beams]}")
                print("-"*100)

            if beam_size == 0:
                break


        # Sort the completed beams
        completed.sort(key=lambda x: x[1], reverse=True)
        # Get target sentence tokens
        target_tokens = completed[0][0]
        # Convert target sentence from tokens to string
        caption = tokenizer.decode(target_tokens, skip_special_tokens=True)
        return caption


def load_model_tokenizer(configs):
    """
    This function will load model and tokenizer from pretrained model and tokenizer
    """
    device = torch.device(configs["device"])
    tokenizer = BertTokenizer.from_pretrained(configs["tokenizer"])  

    # Load model ImageCaptionModel
    model = ImageCaptionModel(
        embedding_dim=configs["embedding_dim"],
        attention_dim=configs["attention_dim"],
        vocab_size=tokenizer.vocab_size,
        max_seq_len=configs["max_seq_len"],
        num_layers=configs["num_layers"],
        num_heads=configs["num_heads"],
        dropout=configs["dropout"],
    )
    model.load_state_dict(torch.load(configs["model"]))
    model.to(device)
    model.eval()
    print(f"Done load model on the {device} device")
    return model, tokenizer, device


# Evaluate model on test dataset
def evaluate():
    if not os.path.exists("results/"):
        os.mkdir("results/")

    # Load model and tokenizer
    model, tokenizer, device = load_model_tokenizer(configs)
    # Load test dataset
    test_dataset = ImageCaptionDataset(
        karpathy_json_path=configs["karpathy_json_path"],
        image_dir=configs["image_dir"],
        tokenizer=tokenizer,
        max_seq_len=configs["max_seq_len"],
        transform=transform, 
        phase="test"
    )
    # Evaluate model
    model.eval()
    
    beam_size = [3, 4, 5]
    scores = {}
    for b in beam_size:
        result = []
        for i in tqdm(range(len(test_dataset))):
            image, all_caps = test_dataset[i]["image"], test_dataset[i]["all_captions_seq"]
            # Preprocess image
            image = preprocess_image(image, transform)
            # Generate caption
            cap = generate_caption(model, image, tokenizer, beam_size=b, device=device)
            result.append({"image_id": test_dataset[i]["image_id"], "caption": cap})
        # Save result
        result_path = f"results/results_beam{b}.json"
        json.dump(result, open(result_path, "w"))
        # Calculate metrics
        score = metric_scores(result_path, ann_path)
        scores["beam{}".format(b)] = score
    
    # Save scores
    json.dump(scores, open(f"results/scores.json", "w"))


def main():
    # Generate caption
    model, tokenizer, device = load_model_tokenizer(configs)
    st = time.time()
    cap = caption(model, "./data/images/test.jpg", tokenizer, configs["transform"], print_process=False)
    cap = caption(
        model=model,
        image_path="./data/images/test.jpg",
        tokenizer=tokenizer,
        transform=tranform,
        max_seq_len=configs["max_seq_len"],
        beam_size=configs["beam_size"],
        device=device,
        print_process=False
    )
    end = time.time()
    print("--- Caption: {}".format(cap))
    print(f"--- Time: {end-st} (s)")


if __name__ == "__main__":
    main()