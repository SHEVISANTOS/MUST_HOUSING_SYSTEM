from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Conversation, Message
from apps.properties.models import Property

# A short set of canned replies shown as one-tap buttons in a thread -
# intentionally generic (not property-specific), matching the brief's
# "quick replies" ask without needing a separate configurable model for it.
QUICK_REPLIES = [
    "Is this still available?",
    "Can I schedule a viewing?",
    "What's the earliest move-in date?",
    "Thank you!",
]


def _conversations_for(user):
    return Conversation.objects.filter(Q(tenant=user) | Q(landlord=user)).select_related(
        'property', 'tenant', 'landlord'
    )


@login_required
def inbox(request):
    conversations = _conversations_for(request.user)
    rows = []
    for conv in conversations:
        last_message = conv.messages.last()
        rows.append({
            'conversation': conv,
            'other_party': conv.other_party(request.user),
            'last_message': last_message,
            'unread_count': conv.unread_count_for(request.user),
        })
    return render(request, 'messaging/inbox.html', {'rows': rows, 'quick_replies': QUICK_REPLIES})


@login_required
def thread(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related('property', 'tenant', 'landlord'),
        id=conversation_id,
    )
    if request.user.id not in (conversation.tenant_id, conversation.landlord_id):
        messages.error(request, "You don't have access to this conversation.")
        return redirect('messaging:inbox')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            Message.objects.create(conversation=conversation, sender=request.user, body=body)
            conversation.save(update_fields=['updated_at'])
        return redirect('messaging:thread', conversation_id=conversation.id)

    # Mark the other party's messages as read now that this user has opened the thread.
    conversation.messages.filter(read_at__isnull=True).exclude(sender=request.user).update(read_at=timezone.now())

    return render(request, 'messaging/thread.html', {
        'conversation': conversation,
        'other_party': conversation.other_party(request.user),
        'messages_list': conversation.messages.select_related('sender'),
        'quick_replies': QUICK_REPLIES,
    })


@login_required
def start_conversation(request, property_id):
    """Entry point from the property detail page's "Ask a question" button."""
    if request.user.role != 'TENANT':
        messages.error(request, "Only tenants can message landlords.")
        return redirect('properties:detail', pk=property_id)

    prop = get_object_or_404(Property, id=property_id)
    if prop.landlord_id == request.user.id:
        messages.error(request, "You can't message yourself about your own listing.")
        return redirect('properties:detail', pk=property_id)

    conversation = Conversation.get_or_create_for(prop, request.user)
    return redirect('messaging:thread', conversation_id=conversation.id)
