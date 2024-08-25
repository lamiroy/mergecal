import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import Value, IntegerField
from django.http import Http404, JsonResponse
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import ListView
from django.views.generic import UpdateView
from rest_framework import status
from rest_framework.decorators import renderer_classes, api_view
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from mergecal.calendars.forms import CalendarForm
from mergecal.calendars.forms import SourceForm
from mergecal.calendars.models import Calendar
from mergecal.calendars.models import Source
from mergecal.calendars.services import CalendarMerger
from mergecal.core.utils import get_site_url

logger = logging.getLogger(__name__)


class UserCalendarListView(LoginRequiredMixin, ListView):
    model = Calendar
    template_name = "calendars/calendar_list.html"
    context_object_name = "calendars"

    def get_queryset(self):
        try:
            v = Calendar.objects.filter(owner=self.request.user) \
                .annotate(source_count=Count("calendarOf")) \
                .prefetch_related(
                Prefetch(
                    "calendarOf",
                    queryset=Source.objects.all()[:5],
                    to_attr="recent_sources",
                ),
            ) \
                .select_related("owner")
            print(v)
            return v
        except ValueError as e:
            v = (
                Calendar.objects.filter(owner=self.request.user)
                .annotate(source_count=Value(0, IntegerField()))
                .annotate(recent_sources=Value(''))
                .select_related("owner")
            )
            return v

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_calendars"] = self.get_queryset().count()
        try:
            context["total_sources"] = sum(
                calendar.source_count for calendar in context["calendars"]
            )
        except ValueError as e:
            context["total_sources"] = 0
            print(f'***BARTERROR*** {e}')

        context["domain_name"] = get_site_url()
        return context

    def get(self, request, *args, **kwargs):
        user = request.user
        calendars = self.get_queryset()

        if False and (user.is_free_tier and calendars.count() == 0):
            messages.info(
                request,
                "To start creating calendars, please sign up for a plan.",
            )
            return redirect(reverse("pricing"))

        return super().get(request, *args, **kwargs)


class CalendarCreateView(LoginRequiredMixin, CreateView):
    model = Calendar
    form_class = CalendarForm
    template_name = "calendars/calendar_form.html"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Calendar created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("calendars:calendar_update", kwargs={"uuid": self.object.uuid})


class CalendarUpdateView(LoginRequiredMixin, UpdateView):
    model = Calendar
    form_class = CalendarForm
    template_name = "calendars/calendar_form.html"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["domain_name"] = get_site_url()
        return context

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Calendar updated successfully.")
        return super().form_valid(form)


class CalendarDeleteView(LoginRequiredMixin, DeleteView):
    model = Calendar
    success_url = reverse_lazy("calendars:calendar_list")
    slug_field = "uuid"
    slug_url_kwarg = "uuid"

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Calendar deleted successfully.")
        return super().delete(request, *args, **kwargs)


class SourceAddView(LoginRequiredMixin, CreateView):
    model = Source
    form_class = SourceForm
    template_name = "calendars/source_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.calendar = get_object_or_404(
            Calendar,
            uuid=self.kwargs["uuid"],
            owner=self.request.user,
        )

    def form_valid(self, form):
        form.instance.calendar.uuid = self.kwargs["uuid"]
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["calendar"] = self.calendar
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["calendar"] = self.calendar
        return kwargs

    def get_success_url(self):
        return reverse(
            "calendars:calendar_update",
            kwargs={"uuid": self.kwargs["uuid"]},
        )


class SourceEditView(LoginRequiredMixin, UpdateView):
    model = Source
    form_class = SourceForm
    template_name = "calendars/source_form.html"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.calendar.owner != self.request.user:
            error_message = "You don't have permission to edit this source."
            raise PermissionDenied(error_message)
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["calendar"] = self.object.calendar
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["calendar"] = self.object.calendar
        return context

    def form_valid(self, form):
        form.instance.calendar = self.object.calendar
        messages.success(self.request, "Source updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "calendars:calendar_update",
            kwargs={"uuid": self.object.calendar.uuid},
        )


@require_POST
@login_required
def source_delete(request, pk):
    source = get_object_or_404(Source, pk=pk, calendar__owner=request.user)
    uuid = source.calendar.uuid
    source.delete()
    messages.success(request, "Source deleted successfully.")
    return redirect("calendars:calendar_update", uuid=uuid)


REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
}


class CalendarFileAPIView(APIView):

    def dispatch(self, request, *args, **kwargs):

        def json_response_handler404(request, exception=None):
            data = {'status': 501, 'message': "Not Implemented"}
            return JsonResponse(data=data, status=501)

        if request.method == 'GET':
            return self.get(request, *args, **kwargs)
        elif request.method == 'POST':
            return self.post(request, *args, **kwargs)
        else:
            logger.info(f"Unhandled dispatch {request}")
            content = {'error': f'Cannot handle {request}'}
            # return Response(content, status=status.HTTP_501_NOT_IMPLEMENTED)
            return json_response_handler404(request)

    def get(self, request, uuid):
        return self.process_calendar_request(uuid)

    def post(self, request, uuid):
        return self.process_calendar_request(uuid)

    def process_calendar_request(self, uuid):
        try:
            calendar = get_object_or_404(
                Calendar.objects.select_related("owner"),
                uuid=uuid,
            )
        except Http404:
            return Response(
                {"error": "Calendar not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            content = {'error': "Unhandled REST request"}
            return Response(content, status=status.HTTP_501_NOT_IMPLEMENTED)

        merger = CalendarMerger(calendar, self.request)
        calendar_str = merger.merge()

        if not calendar_str:
            return Response(
                {"error": "Failed to generate calendar data"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(calendar_str, content_type="text/calendar")
        response["Content-Disposition"] = f'attachment; filename="{uuid}.ics"'  # E702
        if calendar.owner.is_free_tier:
            response["Cache-Control"] = "public, max-age=43200"  # 12 hours in seconds
        return response


def calendar_view(request: HttpRequest, uuid: str) -> HttpResponse:
    calendar = get_object_or_404(Calendar, uuid=uuid)
    logger.info(
        "User %s is viewing the calendar view page for uuid: %s",
        request.user,
        calendar.uuid,
    )
    return render(
        request,
        "calendars/calendar_view.html",
        context={"calendar": calendar},
    )


@xframe_options_exempt
def calendar_iframe(request: HttpRequest, uuid: str) -> HttpResponse:
    calendar = get_object_or_404(Calendar, uuid=uuid)
    referer = request.headers.get("referer")
    logger.info(
        "Iframe request for calendar %s: uuid %s, referer: %s",
        calendar.name,
        calendar.uuid,
        referer or "Unknown",
    )
    return render(request, "calendars/calendar_iframe.html", {"calendar": calendar})
