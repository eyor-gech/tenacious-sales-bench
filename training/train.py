#!/usr/bin/env python3
"""
TenaciousBench Path B — ORPO Training Script
Trains Qwen2.5-7B-Instruct with LoRA via ORPO (Hong et al. 2024).
Uses TRL's ORPOTrainer; no reference model required.

Usage:
    python training/train.py --config training/config.yaml
    python training/train.py --config training/config.yaml --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import yaml


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_preference_dataset(train_file: str, eval_file: str):
    """Load JSONL preference pairs into HuggingFace Dataset format."""
    from datasets import Dataset

    def read_jsonl(path: str) -> list[dict]:
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    train_rows = read_jsonl(train_file)
    eval_rows = read_jsonl(eval_file)

    def to_hf_format(rows: list[dict]) -> Dataset:
        return Dataset.from_list([
            {
                "prompt": r["prompt"],
                "chosen": r["chosen"],
                "rejected": r["rejected"],
            }
            for r in rows
        ])

    return to_hf_format(train_rows), to_hf_format(eval_rows)


def build_model_and_tokenizer(cfg: dict):
    """Load base model with 4-bit quantisation + LoRA adapters."""
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    model_cfg = cfg["model"]
    lora_cfg = cfg["lora"]

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype="bfloat16",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    tokenizer = AutoTokenizer.from_pretrained(
        model_cfg["backbone"],
        revision=model_cfg["revision"],
        trust_remote_code=model_cfg.get("trust_remote_code", False),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_cfg["backbone"],
        revision=model_cfg["revision"],
        quantization_config=bnb_config,
        device_map=model_cfg.get("device_map", "auto"),
        trust_remote_code=model_cfg.get("trust_remote_code", False),
    )

    lora_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg["lora_dropout"],
        target_modules=lora_cfg["target_modules"],
        bias=lora_cfg["bias"],
        task_type=lora_cfg["task_type"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


class LossLogger:
    """Writes train and eval loss to CSV files for reproducibility."""

    def __init__(self, train_csv: str, eval_csv: str):
        self.train_path = Path(train_csv)
        self.eval_path = Path(eval_csv)
        self.train_path.parent.mkdir(parents=True, exist_ok=True)
        self.eval_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_header(self.train_path, ["step", "loss", "learning_rate", "epoch"])
        self._write_header(self.eval_path, ["step", "eval_loss", "epoch"])

    @staticmethod
    def _write_header(path: Path, cols: list[str]) -> None:
        with path.open("w", newline="") as f:
            csv.writer(f).writerow(cols)

    def log_train(self, step: int, loss: float, lr: float, epoch: float) -> None:
        with self.train_path.open("a", newline="") as f:
            csv.writer(f).writerow([step, f"{loss:.6f}", f"{lr:.2e}", f"{epoch:.3f}"])

    def log_eval(self, step: int, eval_loss: float, epoch: float) -> None:
        with self.eval_path.open("a", newline="") as f:
            csv.writer(f).writerow([step, f"{eval_loss:.6f}", f"{epoch:.3f}"])


class KillCriterionCallback:
    """Aborts training if eval_loss > threshold at the configured check step."""

    def __init__(self, check_step: int, max_loss: float):
        self.check_step = check_step
        self.max_loss = max_loss

    def on_evaluate(self, _args, state, control, metrics=None, **kwargs):  # noqa: N802
        if state.global_step == self.check_step:
            eval_loss = metrics.get("eval_loss", float("inf"))
            if eval_loss > self.max_loss:
                print(
                    f"\n[KILL CRITERION] eval_loss={eval_loss:.4f} > {self.max_loss} at step "
                    f"{self.check_step}. Aborting training. Falling back to 3-shot prompted evaluator.",
                    file=sys.stderr,
                )
                control.should_training_stop = True


def run_training(cfg: dict, dry_run: bool = False) -> None:
    t_cfg = cfg["training"]
    out_cfg = cfg["output"]

    Path(out_cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    Path(out_cfg["log_dir"]).mkdir(parents=True, exist_ok=True)

    if dry_run:
        print("Dry run: config validated. Model load skipped.")
        print(f"  Backbone: {cfg['model']['backbone']} @ {cfg['model']['revision']}")
        print(f"  Training pairs: {cfg['data']['num_train_samples']} train / {cfg['data']['num_eval_samples']} eval")
        print(f"  LoRA r={cfg['lora']['r']}, alpha={cfg['lora']['lora_alpha']}")
        print(f"  Epochs={t_cfg['num_train_epochs']}, lr={t_cfg['learning_rate']}, beta={t_cfg['beta']}")
        return

    # LossLogger creates/overwrites CSV files — must come after dry-run gate
    logger = LossLogger(out_cfg["train_loss_csv"], out_cfg["eval_loss_csv"])

    from trl import ORPOConfig, ORPOTrainer  # deferred: not needed for dry-run

    train_dataset, eval_dataset = load_preference_dataset(
        cfg["data"]["train_file"], cfg["data"]["eval_file"]
    )
    model, tokenizer = build_model_and_tokenizer(cfg)

    orpo_config = ORPOConfig(
        output_dir=out_cfg["output_dir"],
        num_train_epochs=t_cfg["num_train_epochs"],
        per_device_train_batch_size=t_cfg["per_device_train_batch_size"],
        per_device_eval_batch_size=t_cfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=t_cfg["gradient_accumulation_steps"],
        learning_rate=t_cfg["learning_rate"],
        warmup_ratio=t_cfg["warmup_ratio"],
        lr_scheduler_type=t_cfg["lr_scheduler_type"],
        max_length=t_cfg["max_seq_length"],
        max_prompt_length=t_cfg["max_prompt_length"],
        beta=t_cfg["beta"],
        logging_steps=t_cfg["logging_steps"],
        eval_steps=t_cfg["eval_steps"],
        save_steps=t_cfg["save_steps"],
        save_total_limit=t_cfg["save_total_limit"],
        load_best_model_at_end=t_cfg["load_best_model_at_end"],
        metric_for_best_model=t_cfg["metric_for_best_model"],
        greater_is_better=t_cfg["greater_is_better"],
        bf16=t_cfg["bf16"],
        fp16=t_cfg["fp16"],
        optim=t_cfg["optim"],
        weight_decay=t_cfg["weight_decay"],
        max_grad_norm=t_cfg["max_grad_norm"],
        seed=t_cfg["seed"],
        report_to=t_cfg.get("report_to", "none"),
        dataloader_num_workers=t_cfg.get("dataloader_num_workers", 0),
        evaluation_strategy="steps",
    )

    kill_cb = KillCriterionCallback(
        check_step=cfg["convergence_kill_criterion"]["check_step"],
        max_loss=cfg["convergence_kill_criterion"]["max_eval_loss_at_check"],
    )

    trainer = ORPOTrainer(
        model=model,
        args=orpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        callbacks=[kill_cb],
    )

    start_time = time.time()
    train_result = trainer.train()
    elapsed = time.time() - start_time

    # Log final metrics
    for log_entry in trainer.state.log_history:
        if "loss" in log_entry and "eval_loss" not in log_entry:
            logger.log_train(
                log_entry.get("step", 0),
                log_entry["loss"],
                log_entry.get("learning_rate", 0.0),
                log_entry.get("epoch", 0.0),
            )
        if "eval_loss" in log_entry:
            logger.log_eval(
                log_entry.get("step", 0),
                log_entry["eval_loss"],
                log_entry.get("epoch", 0.0),
            )

    trainer.save_model(out_cfg["final_model_dir"])
    tokenizer.save_pretrained(out_cfg["final_model_dir"])

    print(f"\nTraining complete in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Final train loss: {train_result.training_loss:.4f}")
    print(f"Model saved to: {out_cfg['final_model_dir']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench ORPO Training")
    p.add_argument("--config", default="training/config.yaml")
    p.add_argument("--dry-run", action="store_true", help="Validate config without loading model")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    run_training(cfg, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
