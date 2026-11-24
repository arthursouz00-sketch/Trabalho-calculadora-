"""Demonstração de integração com WhatsApp (ambiente de testes)."""
from .automation import ChatItem, WhatsAppAutomation
from .gateway import MessagingGateway, SandboxGateway, parse_webhook
from .interpreter import interpret

__all__ = ["ChatItem", "WhatsAppAutomation", "MessagingGateway", "SandboxGateway", "parse_webhook", "interpret"]
