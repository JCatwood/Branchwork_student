from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("git/pull/", views.get_updates, name="get_updates"),
    path(
        "assessment/<slug:assessment_id>/submit/",
        views.submit_assessment,
        name="submit_assessment",
    ),
    path("assessment/<slug:assessment_id>/", views.assessment, name="assessment"),
]
