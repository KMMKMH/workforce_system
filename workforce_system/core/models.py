from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
from django.dispatch import receiver
from pathlib import Path
import uuid


class User(AbstractUser):
    ROLE_CHOICES = [
        ('CEO', 'CEO'),
        ('HR', 'HR'),
        ('MANAGER', 'Manager'),
        ('EMPLOYEE', 'Employee'),
        ('ACCOUNTANT', 'Accountant'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='EMPLOYEE')
    phone = models.CharField(max_length=15, blank=True, null=True)
    face_encoding = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    address = models.TextField(null=True, blank=True)

    department = models.CharField(max_length=100, null=True, blank=True)
    position = models.CharField(max_length=100, null=True, blank=True)

    salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_members'
    )

    biometric_enabled = models.BooleanField(default=False)

    cv = models.FileField(upload_to='cvs/', null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} Profile"
    
    @receiver(post_save, sender=settings.AUTH_USER_MODEL)
    def create_user_profile(sender, instance, created, **kwargs):
        if created:
            Profile.objects.create(user=instance)


    @receiver(post_save, sender=settings.AUTH_USER_MODEL)
    def save_user_profile(sender, instance, **kwargs):
        instance.profile.save()


class Attendance(models.Model):

    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('LOW_HOURS', 'Low Hours'),
        ('ABSENT', 'Absent'),
        ('LEAVE', 'Leave'),
        ('HOLIDAY', 'Holiday'),
        ('WORKING_HOLIDAY', 'Working Holiday'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    date = models.DateField()

    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    worked_hours = models.FloatField(null=True, blank=True)

    is_anomaly = models.BooleanField(default=False)
    anomaly_reason = models.CharField(max_length=255, null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'date']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.status}"
    

class Holiday(models.Model):

    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.date}"


class PayrollAdjustment(models.Model):

    BONUS = "BONUS"

    TYPE_CHOICES = [
        (BONUS, "Bonus"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payroll_adjustments"
    )

    adjustment_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=BONUS
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    month = models.DateField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_payroll_adjustments"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month", "-created_at"]
        indexes = [
            models.Index(fields=["user", "month"]),
            models.Index(fields=["adjustment_type", "month"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_adjustment_type_display()} - {self.amount}"


class Conversation(models.Model):

    DIRECT = "DIRECT"
    TEAM = "TEAM"
    ANNOUNCEMENT = "ANNOUNCEMENT"

    TYPE_CHOICES = [
        (DIRECT, "Direct"),
        (TEAM, "Team"),
        (ANNOUNCEMENT, "Announcements"),
    ]

    conversation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=150)
    direct_key = models.CharField(max_length=80, unique=True, null=True, blank=True)
    team_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="team_conversations"
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ChatParticipant",
        related_name="chat_conversations"
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at", "title"]
        indexes = [
            models.Index(fields=["conversation_type"]),
            models.Index(fields=["team_manager"]),
        ]

    def __str__(self):
        return self.title


class ChatParticipant(models.Model):

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conversation", "user")
        indexes = [
            models.Index(fields=["user", "conversation"]),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.conversation.title}"


class ChatMessage(models.Model):

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.sender.username}: {self.body[:40]}"
    

class Task(models.Model):

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('READY', 'Ready for Review'),
        ('REVIEW', 'Under Review'),
        ('DONE', 'Done'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_tasks'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    deadline = models.DateTimeField(null=True, blank=True)

    estimated_hours = models.FloatField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.assigned_to.username}"
    

class TaskCommit(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="commits")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_edited(self):
        return abs((self.updated_at - self.created_at).total_seconds()) > 2

    def __str__(self):
        return f"{self.user} - {self.task} ({self.created_at.date()})"    


def task_image_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"task_images/{timestamp}_{uuid.uuid4().hex[:8]}{suffix}"


class TaskImage(models.Model):

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='images'
    )

    image = models.ImageField(upload_to=task_image_upload_path)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    caption = models.CharField(max_length=255, null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.task.title}"
